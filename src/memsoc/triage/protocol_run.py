"""
Test protocol v1 -- the three-arm memory test for one LLM, run the same
way on every tester's machine.

    python -m memsoc.triage.protocol_run --model <model> --preflight
    python -m memsoc.triage.protocol_run --model <model>
    python -m memsoc.triage.protocol_run --model <model> --status
    python -m memsoc.triage.protocol_run --model <model> --verify
    python -m memsoc.triage.protocol_run --model <model> --package

<model> is one of gpt-oss-20b, qwen3.8-27b, gemma-4-26b. Everything else
-- the alerts, the arms, their order, the prompt, the output cap, the
memory settings -- is fixed here and cannot be changed from the command
line. Tester instructions: docs/status/testing-protocol-v1.md.

How this relates to triage_runner.py. Every verdict is produced by the
same triage_runner.triage_alert() and stored by the same write_back(),
with the arm decided only by which memory layer is passed in. What this
module adds is scheduling: it walks the first PROTOCOL_ALERTS alerts in
stream order and, for each alert, triages it in Arm A, then B-self, then
B-oracle before moving to the next. The three arms therefore stop on the
same prefix and run in the same time window, which three separate
processes on a remote tester's machine could not guarantee.

Exit codes: 0 finished or check passed, 1 an error or a failed check
(stop and report), 2 a daily quota was hit under --no-wait.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from memsoc import paths

PROTOCOL = "p1"
PROTOCOL_TAG = "memsoc-protocol-v1"
PROTOCOL_ALERTS = 165

# --model value -> (provider, exact model id, tag used in run ids).
MODELS = {
    "gpt-oss-20b": ("groq", "openai/gpt-oss-20b", "gptoss20b"),
    "qwen3.8-27b": ("groq", "qwen/qwen3.8-27b", "qwen38-27b"),
    "gemma-4-26b": ("gemini", "gemma-4-26b-a4b-it", "gemma4-26b"),
}

# (memory condition, run-id prefix), in the order each alert is triaged.
ARMS = (("off", "armA"), ("self", "bself"), ("oracle", "boracle"))

# The two direct pins (requirements/memory.txt) plus the transitive packages
# that decide the embedding floats, as installed through
# requirements/memory-protocol-v1-constraints.txt.
REQUIRED_PACKAGES = {
    "chromadb": "1.5.9",
    "sentence-transformers": "6.1.0",
    "torch": "2.14.1",
    "transformers": "5.19.0",
    "tokenizers": "0.23.3",
    "numpy": "2.5.3",
}

# The data bundle every tester receives (stream v2, 120,000 flows, seed 42).
DATA_SHA256 = {
    "generated_logs.jsonl": "74869ad4b38d5a8af2a005a924fd6a12d1e63115723739dea49153a27fe40422",
    "ground_truth.csv": "125e60b6b7bccd59fe4ce648f14990f43caf73b4c5a7fa23c94f6b5b5aaf8e40",
    "live_results.jsonl": "0de0f9b94df81510f52bdff8e99fa2c4dfbc8359e409e850916bd857c67b4c31",
}

TOTAL_ALERTS = 1135

# SHA-256 of the first PROTOCOL_ALERTS uids joined by "\n", in stream order.
FIRST_UIDS_SHA256 = "36f2dc87c09a6c24bb9154ef856f13950f53581cb00e2eaaf953d7ffe5856f60"

# SHA-256 of the Arm A prompt for alert 0. Proves the same template, data
# and renderer on every machine.
ALERT0_PROMPT_SHA256 = "99c220e48db5bd915aa0ee83c2572f17e8f59eed46c6cf77c6c417d0377ee6ae"

# The stream positions (seq) of the past alerts memory retrieves for each
# of the first 165 alerts, most similar first. Retrieval embeds the alert
# only (decisions.md C1), so it does not depend on the model or on the
# stored verdicts: recorded from boracle-flashlite-20261015, where B-self
# and B-oracle agreed on all 165. A tester whose list differs has a
# different embedding environment. One list per alert, in the JSON file
# beside this module.
_EXPECTED_RETRIEVAL_FILE = Path(__file__).with_name("protocol_p1_retrieval.json")

# Seconds to sleep between checks while a daily quota is used up.
QUOTA_WAIT_FALLBACK = 3600
QUOTA_WAIT_MAX = 6 * 3600

PARSE_MAX_ATTEMPTS = 3
NETWORK_MAX_RETRIES = 10
NETWORK_RETRY_WAIT = 60


# ----------------------------------------------------------------------
# Setup that must happen before config is imported.
# ----------------------------------------------------------------------

def _load_env_file():
    """
    Read GROQ_API_KEY / GEMINI_API_KEY from the repo's .env, without
    overriding anything already set. Testers do not export variables by
    hand; only these two keys are read.
    """

    env_path = Path(paths.ROOT) / ".env"

    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():

        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key in ("GROQ_API_KEY", "GEMINI_API_KEY") and value and key not in os.environ:
            os.environ[key] = value


def _select_model(model_flag):
    """Fix the provider and model for this process, before config loads."""

    provider, model_id, _ = MODELS[model_flag]

    os.environ["TRIAGE_PROVIDER"] = provider
    os.environ["TRIAGE_MODEL"] = model_id


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

class Log:
    """Prints and appends every line, timestamped, to this model's log."""

    def __init__(self, path):

        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, message="", error=False):

        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for line in str(message).splitlines() or [""]:
            text = f"[{stamp}] {line}"
            print(text, file=sys.stderr if error else sys.stdout, flush=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(text + "\n")


def _sha256(path):

    digest = hashlib.sha256()

    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)

    return digest.hexdigest()


def _data_paths():

    return {
        "generated_logs.jsonl": Path(paths.GENERATED_LOGS),
        "ground_truth.csv": Path(paths.GROUND_TRUTH),
        "live_results.jsonl": Path(paths.LIVE_RESULTS),
    }


def _git(*args):

    try:
        out = subprocess.run(
            ["git", *args], cwd=paths.ROOT, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    return out.stdout.strip() if out.returncode == 0 else None


def _run_ids(tag):

    return {condition: f"{prefix}-{tag}-{PROTOCOL}" for condition, prefix in ARMS}


def _verdicts_path(run_id):

    return Path(paths.run_dir(run_id)) / "triage_verdicts.jsonl"


def _load_expected_retrieval():

    with open(_EXPECTED_RETRIEVAL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _precedent_seqs(row):

    return [int(c.rsplit(":", 1)[1]) for c in row.get("precedent_used", "").split(",") if c]


# ----------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------

def _checks(model_flag, with_api):
    """
    Every check the run depends on, as (name, status, detail) with status
    PASS, FAIL or WARN. Loads the alerts too, and returns them so the run
    does not read 200 MB twice.
    """

    from memsoc.memory import embedding
    from memsoc.triage import config, llm_client, triage_prompt, triage_runner

    results = []
    loaded = {}

    def add(name, ok, detail="", warn=False):
        results.append((name, "PASS" if ok else ("WARN" if warn else "FAIL"), detail))

    version = platform.python_version()
    add("Python 3.13", version.startswith("3.13."), version)

    for package, wanted in REQUIRED_PACKAGES.items():
        try:
            found = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            found = "not installed"
        add(f"{package}=={wanted}", found == wanted, found)

    commit = _git("rev-parse", "HEAD")
    tag_commit = _git("rev-list", "-n", "1", PROTOCOL_TAG)
    add("git checkout is the protocol tag", bool(commit) and commit == tag_commit,
        f"HEAD {commit or '?'}; {PROTOCOL_TAG} {tag_commit or 'not found'}")

    dirty = _git("status", "--porcelain", "--", "src", "tests", "requirements")
    add("no local changes to src/, tests/, requirements/", dirty == "",
        "clean" if dirty == "" else (dirty or "git not available"))

    for name, path in _data_paths().items():
        if not path.exists():
            add(f"data file {name}", False, f"missing: {path}")
            continue
        digest = _sha256(path)
        add(f"data file {name}", digest == DATA_SHA256[name], digest[:16] + "...")

    if not all(Path(p).exists() for p in _data_paths().values()):
        return results, loaded

    alerts = triage_runner.load_alerts()
    flows = triage_runner.load_flows()
    add(f"{TOTAL_ALERTS} detector alerts", len(alerts) == TOTAL_ALERTS, str(len(alerts)))

    first = alerts[:PROTOCOL_ALERTS]
    uid_digest = hashlib.sha256("\n".join(a["uid"] for a in first).encode()).hexdigest()
    add(f"first {PROTOCOL_ALERTS} alerts", uid_digest == FIRST_UIDS_SHA256, uid_digest[:16] + "...")

    missing = [a["uid"] for a in first if a["uid"] not in flows]
    add("every alert joins its flow", not missing, f"{len(missing)} missing")

    if first and not missing:
        prompt = triage_prompt.render(first[0], flows[first[0]["uid"]])
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        add("Arm A prompt for alert 0", digest == ALERT0_PROMPT_SHA256, digest[:16] + "...")

    try:
        vector = embedding.embed("protocol preflight")
        add("embedding model loads", len(vector) == embedding.EMBEDDING_DIM,
            f"{embedding.MODEL_NAME} @ {embedding.MODEL_REVISION[:10]}")
    except Exception as e:
        add("embedding model loads", False, f"{type(e).__name__}: {e}")

    provider, model_id, _ = MODELS[model_flag]
    key = config.GROQ_API_KEY if provider == "groq" else config.GEMINI_API_KEY
    key_set = bool(key) and key != config.GROQ_API_KEY_PLACEHOLDER
    add(f"{'GROQ' if provider == 'groq' else 'GEMINI'}_API_KEY in .env", key_set,
        "set" if key_set else "missing")

    add("model selected", config.TRIAGE_MODEL == model_id and config.TRIAGE_PROVIDER == provider,
        f"{config.TRIAGE_PROVIDER} {config.TRIAGE_MODEL}")

    if with_api and key_set:
        try:
            text, latency = llm_client.call_triage_llm(
                'Reply with exactly this JSON object and nothing else: {"ok": true}'
            )
            ok = json.loads(text).get("ok") is True
            add("API answers in JSON mode", ok, f"{latency / 1000:.1f}s")
        except Exception as e:
            add("API answers in JSON mode", False, f"{type(e).__name__}: {str(e)[:300]}")

    remaining = llm_client.budget_remaining(provider, model_id)
    add("local daily request budget", remaining > 0, f"{remaining} requests left today")

    loaded.update(alerts=alerts, flows=flows, first=first)

    return results, loaded


def _print_checks(log, results):

    for name, status, detail in results:
        log(f"  {status:4}  {name}" + (f"  ({detail})" if detail else ""))

    failed = [r for r in results if r[1] == "FAIL"]
    log(f"RESULT: {'FAIL' if failed else 'PASS'} -- {len(failed)} check(s) failed")

    return not failed


# ----------------------------------------------------------------------
# run_config.json
# ----------------------------------------------------------------------

def _run_config(model_flag, run_id, condition):

    from memsoc.memory import case_text, embedding, store
    from memsoc.triage import config

    provider, model_id, _ = MODELS[model_flag]

    return {
        "protocol": PROTOCOL,
        "protocol_tag": PROTOCOL_TAG,
        "git_commit": _git("rev-parse", "HEAD"),
        "run_id": run_id,
        "memory_condition": condition,
        "alerts": PROTOCOL_ALERTS,
        "arm_order": [c for c, _ in ARMS],
        "provider": provider,
        "model_id": model_id,
        "temperature": config.TEMPERATURE if provider == "groq" else config.GEMINI_TEMPERATURE,
        "max_output_tokens": config.TRIAGE_MAX_RESPONSE_TOKENS,
        "json_mode": config.TRIAGE_JSON_MODE,
        "reasoning": "model default",
        "embedding_model": embedding.MODEL_NAME,
        "embedding_revision": embedding.MODEL_REVISION,
        "case_schema": case_text.SCHEMA_VERSION,
        "top_k": store.TOP_K,
        "similarity_cutoff": None,
        "write_policy": store.WRITE_POLICY,
        "alert0_prompt_sha256": ALERT0_PROMPT_SHA256,
        "data_sha256": DATA_SHA256,
        "packages": {p: importlib.metadata.version(p) for p in REQUIRED_PACKAGES},
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


# Fields that must not change once a run has started.
_FROZEN_FIELDS = ("protocol", "git_commit", "provider", "model_id", "alerts",
                  "max_output_tokens", "json_mode", "embedding_revision", "data_sha256")


def _ensure_run_config(log, model_flag, run_id, condition):

    path = Path(paths.run_dir(run_id)) / "run_config.json"
    current = _run_config(model_flag, run_id, condition)

    if path.exists():

        recorded = json.loads(path.read_text(encoding="utf-8"))
        changed = [k for k in _FROZEN_FIELDS if recorded.get(k) != current.get(k)]

        if changed:
            log(f"ERROR: {run_id} was started under different settings: {changed}.", error=True)
            log("Do not delete anything. Stop and send this message to Aryan.", error=True)
            sys.exit(1)

        return

    current["started_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=1), encoding="utf-8")


# ----------------------------------------------------------------------
# The run
# ----------------------------------------------------------------------

def _quota_wait(error):

    wait = error.retry_after if error.retry_after else QUOTA_WAIT_FALLBACK

    return min(max(wait + 30, 60), QUOTA_WAIT_MAX)


def _triage_with_retries(log, record, flow, seq, mem, run_id):
    """
    One verdict, retried on an unparseable answer or a dropped connection.
    Raises DailyBudgetExhausted untouched; anything else after the retries
    is raised to stop the run.
    """

    import requests

    from memsoc.triage import llm_client, triage_runner

    parse_failures = 0
    network_failures = 0

    while True:
        try:
            row = triage_runner.triage_alert(record, flow, seq, mem, run_id)
            row["protocol"] = PROTOCOL
            row["attempts"] = parse_failures + network_failures + 1
            row.update({f"usage_{k}": v for k, v in llm_client.LAST_USAGE.items()})
            return row

        except llm_client.DailyBudgetExhausted:
            raise

        except ValueError as e:
            parse_failures += 1
            if parse_failures >= PARSE_MAX_ATTEMPTS:
                raise
            log(f"  answer was not a valid verdict ({str(e)[:120]}); retrying "
                f"{parse_failures}/{PARSE_MAX_ATTEMPTS - 1}", error=True)

        except (requests.ConnectionError, requests.Timeout) as e:
            network_failures += 1
            if network_failures > NETWORK_MAX_RETRIES:
                raise
            log(f"  network error ({type(e).__name__}); waiting {NETWORK_RETRY_WAIT}s, "
                f"retry {network_failures}/{NETWORK_MAX_RETRIES}", error=True)
            time.sleep(NETWORK_RETRY_WAIT)


def run(log, model_flag, wait_on_quota):

    from memsoc.memory import open_memory
    from memsoc.triage import config, llm_client, triage_runner

    results, loaded = _checks(model_flag, with_api=False)

    if not _print_checks(log, results):
        log("Not starting: fix the FAIL lines above (see the protocol doc, Troubleshooting).", error=True)
        sys.exit(1)

    provider, model_id, tag = MODELS[model_flag]
    run_ids = _run_ids(tag)
    first, flows = loaded["first"], loaded["flows"]

    for condition, run_id in run_ids.items():
        _ensure_run_config(log, model_flag, run_id, condition)

    mems = {condition: open_memory(run_id, condition) for condition, run_id in run_ids.items()}
    done = {condition: triage_runner.load_done_rows(_verdicts_path(run_id))
            for condition, run_id in run_ids.items()}

    by_uid = {a["uid"]: a for a in first}

    for condition in ("self", "oracle"):
        rows = sorted(done[condition].values(), key=lambda r: r["seq"])
        for row in rows:
            triage_runner.write_back(mems[condition], by_uid[row["uid"]], flows[row["uid"]], row)

    total = PROTOCOL_ALERTS * len(ARMS)
    completed = sum(len(rows) for rows in done.values())
    log(f"{model_id}: {completed} of {total} verdicts already done; {total - completed} to go")

    pace = config.GEMINI_PACE_SECONDS if provider == "gemini" else config.TRIAGE_PACE_SECONDS
    calls = 0

    try:
        for seq, record in enumerate(first):

            uid = record["uid"]

            for condition, _ in ARMS:

                if uid in done[condition]:
                    continue

                run_id = run_ids[condition]

                while True:

                    if calls:
                        time.sleep(pace)
                    calls += 1

                    try:
                        row = _triage_with_retries(log, record, flows[uid], seq, mems[condition], run_id)
                        break

                    except llm_client.DailyBudgetExhausted as e:
                        if not wait_on_quota:
                            log(f"Daily quota reached: {str(e).splitlines()[0]}", error=True)
                            log("Run the same command again after the quota resets.", error=True)
                            sys.exit(2)
                        wait = _quota_wait(e)
                        until = datetime.now() + timedelta(seconds=wait)
                        log(f"Daily quota reached. Waiting {wait / 60:.0f} min, until about "
                            f"{until:%H:%M}, then continuing automatically. Leave this window open.")
                        time.sleep(wait)

                triage_runner.append_verdict(row, _verdicts_path(run_id))
                triage_runner.write_back(mems[condition], record, flows[uid], row)
                done[condition][uid] = row
                completed += 1

                log(f"[{completed}/{total}] alert {seq + 1}/{PROTOCOL_ALERTS} {condition:6} "
                    f"verdict={row['verdict']} category={row['attack_category']} "
                    f"conf={row['confidence']} precedents={row['precedent_count']} "
                    f"tokens={row.get('usage_total_tokens')} {row['latency_ms'] / 1000:.0f}s")

    except KeyboardInterrupt:
        log("Stopped by Ctrl-C. Everything written so far is kept; run the same command to continue.")
        sys.exit(130)

    except Exception as e:
        log(f"ERROR on alert {uid}: {type(e).__name__}: {str(e)[:1500]}", error=True)
        log("Everything written so far is kept. Follow the protocol doc's Troubleshooting table.", error=True)
        sys.exit(1)

    for mem in mems.values():
        if getattr(mem, "skipped_writes", 0):
            log(f"WARNING: {mem.skipped_writes} memory writes failed -- report this to Aryan.", error=True)

    log(f"DONE: all {total} verdicts written. Next: run with --verify.")


# ----------------------------------------------------------------------
# Status, verify, package
# ----------------------------------------------------------------------

def status(log, model_flag):

    from memsoc.triage import triage_runner

    _, model_id, tag = MODELS[model_flag]

    for condition, run_id in _run_ids(tag).items():
        rows = triage_runner.load_done_rows(_verdicts_path(run_id))
        log(f"  {run_id:28} {len(rows):3} of {PROTOCOL_ALERTS} verdicts")


def verify(log, model_flag):

    from memsoc.triage import triage_runner

    _, model_id, tag = MODELS[model_flag]
    run_ids = _run_ids(tag)
    results = []

    def add(name, ok, detail="", warn=False):
        results.append((name, "PASS" if ok else ("WARN" if warn else "FAIL"), detail))

    rows = {}
    configs = {}

    for condition, run_id in run_ids.items():

        by_seq = {r["seq"]: r for r in triage_runner.load_done_rows(_verdicts_path(run_id)).values()}
        rows[condition] = by_seq

        add(f"{run_id}: {PROTOCOL_ALERTS} verdicts", sorted(by_seq) == list(range(PROTOCOL_ALERTS)),
            f"{len(by_seq)} found")
        add(f"{run_id}: one model", {r.get("model_id") for r in by_seq.values()} == {model_id},
            ", ".join(sorted({str(r.get('model_id')) for r in by_seq.values()})))

        config_path = Path(paths.run_dir(run_id)) / "run_config.json"
        configs[condition] = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        add(f"{run_id}: run_config.json", bool(configs[condition]))

    add("same alerts in all three arms",
        len({tuple(r["uid"] for _, r in sorted(rows[c].items())) for c in rows}) == 1)

    add("Arm A retrieved nothing", all(r["precedent_count"] == 0 for r in rows["off"].values()))
    add("Arm A created no memory store", not Path(paths.memory_store(run_ids["off"])).exists())

    for condition in ("self", "oracle"):
        add(f"{run_ids[condition]}: memory store exists",
            Path(paths.memory_store(run_ids[condition])).exists())

    frozen = {c: {k: configs[c].get(k) for k in _FROZEN_FIELDS} for c in configs}
    add("same settings in all three arms", len({json.dumps(v, sort_keys=True) for v in frozen.values()}) == 1)

    self_seqs = [_precedent_seqs(rows["self"][s]) for s in sorted(rows["self"])]
    oracle_seqs = [_precedent_seqs(rows["oracle"][s]) for s in sorted(rows["oracle"])]
    add("B-self and B-oracle retrieved the same past alerts", self_seqs == oracle_seqs)

    expected = _load_expected_retrieval()
    differ = sum(1 for got, want in zip(oracle_seqs, expected) if got != want)
    add("retrieval matches the reference machine", differ == 0,
        f"{differ} of {len(expected)} alerts differ", warn=True)

    ok = _print_checks(log, results)

    log("")
    log("Scores (memsoc.triage.score_verdicts, unchanged):")

    for condition, run_id in run_ids.items():
        out = subprocess.run(
            [sys.executable, "-m", "memsoc.triage.score_verdicts", "--verdicts", str(_verdicts_path(run_id))],
            capture_output=True, text=True, cwd=paths.ROOT,
        )
        log(out.stdout.strip() or out.stderr.strip())

    return ok


def package(log, model_flag):

    _, _, tag = MODELS[model_flag]
    run_ids = _run_ids(tag)

    if not verify(log, model_flag):
        log("Not packaging: --verify has FAIL lines. Send the verify output to Aryan instead.", error=True)
        sys.exit(1)

    target = Path(paths.ARTIFACTS_DIR) / f"memsoc-{PROTOCOL}-{tag}-results.zip"

    # Laid out as runs/<run_id>/... and memory/<run_id>/..., so the zip
    # unpacks straight into artifacts/ on the receiving machine.
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:

        for run_id in run_ids.values():
            for kind, base in (("runs", Path(paths.run_dir(run_id))),
                               ("memory", Path(paths.memory_store(run_id)))):
                if base.exists():
                    for f in base.rglob("*"):
                        if f.is_file():
                            z.write(f, f"{kind}/{run_id}/{f.relative_to(base).as_posix()}")

        z.write(log.path, f"runs/{log.path.name}")

    log(f"PACKAGED: {target}  ({target.stat().st_size / 1e6:.1f} MB). Send this file to Aryan.")


# ----------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(description="MemSOC test protocol v1 -- three arms, one model")
    parser.add_argument("--model", required=True, choices=sorted(MODELS))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true", help="check everything, make one API call, exit")
    mode.add_argument("--status", action="store_true", help="show progress and exit")
    mode.add_argument("--verify", action="store_true", help="check the finished runs and print scores")
    mode.add_argument("--package", action="store_true", help="verify, then zip the results for Aryan")
    parser.add_argument("--no-wait", action="store_true",
                        help="exit with code 2 at a daily quota instead of waiting")
    args = parser.parse_args()

    _load_env_file()
    _select_model(args.model)

    _, model_id, tag = MODELS[args.model]
    log = Log(Path(paths.RUNS_DIR) / f"protocol-{tag}-{PROTOCOL}.log")

    log(f"=== protocol {PROTOCOL} | model {model_id} | "
        f"{'preflight' if args.preflight else 'status' if args.status else 'verify' if args.verify else 'package' if args.package else 'run'} ===")

    if args.preflight:
        results, _ = _checks(args.model, with_api=True)
        sys.exit(0 if _print_checks(log, results) else 1)

    if args.status:
        status(log, args.model)
        return

    if args.verify:
        sys.exit(0 if verify(log, args.model) else 1)

    if args.package:
        package(log, args.model)
        return

    run(log, args.model, wait_on_quota=not args.no_wait)


if __name__ == "__main__":
    main()
