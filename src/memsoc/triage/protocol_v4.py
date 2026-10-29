"""
Test protocol v4 -- the supplementary memory experiments, Gemma only.

    python -m memsoc.triage.protocol_v4 --experiment <name> --preflight
    python -m memsoc.triage.protocol_v4 --experiment <name> --dry-run
    python -m memsoc.triage.protocol_v4 --experiment <name>
    python -m memsoc.triage.protocol_v4 --experiment <name> --status
    python -m memsoc.triage.protocol_v4 --experiment <name> --verify

<name> is a key of EXPERIMENTS. Each experiment is ONE memory arm, run
either over the same 165 alerts as protocol v3 or over a benign set
built by protocol_v4_benign.py, and is compared against the frozen v3
results (armA/bself/boracle-gemma4-26b-p3), which this module never
opens for writing. Those results stay the main experiment; every run
made here is supplementary. The B-self benign arms start from a copy of
the p3 B-self store (attack-primed memory) and keep writing back.

How this relates to protocol_run.py (v3). Everything that decides a
verdict is shared, not copied: the same environment and data checks,
the same alerts, the same triage_runner.triage_alert() and write_back(),
the same retry policy. The arm is decided only by which memory condition
is passed to open_memory(). What v4 adds:

- its own tag (memsoc-protocol-v4) and run ids ending in -p4, so no v4
  run can land in a v3 directory;
- a gate: no real run starts until the pre-registration note is
  committed and HEAD is the v4 tag;
- --dry-run, which makes DRY_RUN_ALERTS real calls into a separate
  -dryrun run id, with the tag and clean-tree checks downgraded to WARN,
  so the code can be exercised before the tag exists;
- a hash of the alert order, recorded in run_config.json.

Stopping and resuming. Ctrl-C at any point keeps every verdict already
written. Running the same command again rebuilds memory from those
verdicts and continues from the next alert, at no API cost.

Exit codes: 0 finished or check passed, 1 an error or a failed check,
2 a daily quota was hit under --no-wait.
"""

import argparse
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from memsoc import paths
from memsoc.triage import protocol_run

PROTOCOL = "p4"
PROTOCOL_TAG = "memsoc-protocol-v4"

# Gemma only: v4 extends the Gemma p3 result and nothing else.
MODEL = "gemma-4-26b"

# One arm per experiment. "alerts" names the alerts it triages: "p3" is
# the first 165 stream alerts; "hard" and "random" are the benign sets
# built by protocol_v4_benign.py. "seed_store" is a p3 memory store the
# run starts from, copied, never opened in place.
EXPERIMENTS = {
    "shuffled": {"condition": "shuffled", "prefix": "bshuf", "alerts": "p3"},
    "benign-armA": {"condition": "off", "prefix": "armA-benign", "alerts": "hard"},
    "benign-bself": {"condition": "self", "prefix": "bself-benign", "alerts": "hard",
                     "seed_store": "bself-gemma4-26b-p3"},
    "random-armA": {"condition": "off", "prefix": "armA-randbenign", "alerts": "random"},
    "random-bself": {"condition": "self", "prefix": "bself-randbenign", "alerts": "random",
                     "seed_store": "bself-gemma4-26b-p3"},
}

# The p3 B-self store as received and verified (BL-171): its case count
# and the SHA-256 of its chroma.sqlite3. A seeded run refuses any other.
SEED_STORES = {
    "bself-gemma4-26b-p3": (165, "fd5ba38c3143d7918d4685aba762b1b1fccee070c0ea4386b3ebe67c1de31d55"),
}

# Committed before the first real run, so it is time-stamped by git.
PREREGISTRATION = "docs/status/protocol-v4-preregistration.md"

# Two, not one: the first alert meets an empty store and retrieves
# nothing, so only the second exercises the memory condition.
DRY_RUN_ALERTS = 2

# p3 checks whose FAIL becomes a WARN under --dry-run, and only then.
_DRY_RUN_TOLERATED = (
    "git checkout is the protocol tag",
    "pre-registration note is committed",
    "no local changes to src/, tests/, requirements/",
    "benign list is committed",
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _run_id(experiment, dry_run=False):

    prefix = EXPERIMENTS[experiment]["prefix"]
    _, _, tag = protocol_run.MODELS[MODEL]

    return f"{prefix}-{tag}-{PROTOCOL}" + ("-dryrun" if dry_run else "")


def _alert_order_sha256(alerts):
    """SHA-256 of the uids joined by "\\n", in the order they are triaged."""

    return hashlib.sha256("\n".join(a["uid"] for a in alerts).encode()).hexdigest()


def _alerts(experiment, loaded, dry_run):
    """
    (alerts in run order, flows by uid, seq of the first alert).

    Benign alerts are numbered on from the 165 attacks, so in a seeded
    store their cases follow the p3 cases rather than reusing their seqs.
    """

    source = EXPERIMENTS[experiment]["alerts"]

    if source == "p3":
        alerts, flows, start = loaded["first"], loaded["flows"], 0
    else:
        from memsoc.triage import protocol_v4_benign
        alerts, flows = protocol_v4_benign.load(source)
        start = protocol_run.PROTOCOL_ALERTS

    return (alerts[:DRY_RUN_ALERTS] if dry_run else alerts), flows, start


def _seed_memory(log, experiment, run_id):
    """
    Seeded experiments only. Copy the verified p3 store to this run's
    store before it is first opened, checking the source and the copy
    against SEED_STORES. A resumed run already has its store: no copy.
    """

    import shutil

    seed = EXPERIMENTS[experiment].get("seed_store")
    target = Path(paths.memory_store(run_id))

    if not seed or target.exists():
        return

    source = Path(paths.P3_GEMMA_RESULTS) / "memory" / seed
    _, wanted = SEED_STORES[seed]

    found = protocol_run._sha256(source / "chroma.sqlite3") if source.exists() else "missing"

    if found != wanted:
        log(f"ERROR: seed store {source} has chroma.sqlite3 {found}, expected {wanted}.", error=True)
        sys.exit(1)

    shutil.copytree(source, target)

    copied = protocol_run._sha256(target / "chroma.sqlite3")

    if copied != wanted:
        log(f"ERROR: the copy at {target} has chroma.sqlite3 {copied}, expected {wanted}.", error=True)
        sys.exit(1)

    log(f"Seeded {run_id} from {seed}: chroma.sqlite3 {copied}")


# ----------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------

def _checks(with_api, dry_run, experiment=None):
    """
    The v3 checks, with v3's tag check replaced by v4's, plus the
    pre-registration gate and, for a benign experiment, the benign list.
    Under --dry-run the tag, note, list-committed and clean-tree checks
    warn instead of failing; every other check still fails.
    """

    results, loaded = protocol_run._checks(MODEL, with_api)

    results = [r for r in results if r[0] != "git checkout is the protocol tag"]

    def add(name, ok, detail=""):
        results.append((name, "PASS" if ok else "FAIL", detail))

    commit = protocol_run._git("rev-parse", "HEAD")
    tag_commit = protocol_run._git("rev-list", "-n", "1", PROTOCOL_TAG)
    add("git checkout is the protocol tag", bool(commit) and commit == tag_commit,
        f"HEAD {commit or '?'}; {PROTOCOL_TAG} {tag_commit or 'not found'}")

    tracked = protocol_run._git("ls-files", "--error-unmatch", PREREGISTRATION)
    unchanged = protocol_run._git("status", "--porcelain", "--", PREREGISTRATION) == ""
    note_commit = protocol_run._git("log", "-1", "--format=%h %cI", "--", PREREGISTRATION)
    add("pre-registration note is committed", bool(tracked) and unchanged,
        note_commit or f"{PREREGISTRATION} not committed")

    source = EXPERIMENTS[experiment]["alerts"] if experiment else "p3"

    if source != "p3":

        from memsoc.triage import protocol_v4_benign

        listing = str(protocol_v4_benign.MANIFEST.relative_to(paths.ROOT)).replace("\\", "/")
        committed = (bool(protocol_run._git("ls-files", "--error-unmatch", listing))
                     and protocol_run._git("status", "--porcelain", "--", listing) == "")
        add("benign list is committed", committed, listing)

        ok, detail = protocol_v4_benign.check(source)
        add(f"{source} benign files match the list", ok, detail)

    if dry_run:
        results = [
            (name, "WARN" if status == "FAIL" and name in _DRY_RUN_TOLERATED else status, detail)
            for name, status, detail in results
        ]

    return results, loaded


# ----------------------------------------------------------------------
# run_config.json
# ----------------------------------------------------------------------

def _run_config(experiment, run_id, alerts, dry_run):

    condition = EXPERIMENTS[experiment]["condition"]
    seed = EXPERIMENTS[experiment].get("seed_store")

    current = protocol_run._run_config(MODEL, run_id, condition)

    current.update({
        "protocol": PROTOCOL,
        "protocol_tag": PROTOCOL_TAG,
        "experiment": experiment,
        "dry_run": dry_run,
        "alerts": len(alerts),
        "alert_source": EXPERIMENTS[experiment]["alerts"],
        "seed_store": seed,
        "seed_store_sha256": SEED_STORES[seed][1] if seed else None,
        "arm_order": [condition],
        "alert_order_sha256": _alert_order_sha256(alerts),
        "preregistration": protocol_run._git("log", "-1", "--format=%H", "--", PREREGISTRATION),
        "compared_against": [f"{prefix}-{protocol_run.MODELS[MODEL][2]}-{protocol_run.PROTOCOL}"
                             for _, prefix in protocol_run.ARMS],
    })

    return current


_FROZEN_FIELDS = protocol_run._FROZEN_FIELDS + ("experiment", "alert_order_sha256")


def _ensure_run_config(log, experiment, run_id, alerts, dry_run):

    path = Path(paths.run_dir(run_id)) / "run_config.json"
    current = _run_config(experiment, run_id, alerts, dry_run)

    if path.exists():

        recorded = json.loads(path.read_text(encoding="utf-8"))
        changed = [k for k in _FROZEN_FIELDS if recorded.get(k) != current.get(k)]

        if changed:
            log(f"ERROR: {run_id} was started under different settings: {changed}.", error=True)
            log("Do not delete anything. Stop and report this to the team.", error=True)
            sys.exit(1)

        return

    current["started_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=1), encoding="utf-8")


# ----------------------------------------------------------------------
# The run
# ----------------------------------------------------------------------

def run(log, experiment, wait_on_quota, dry_run=False):

    from memsoc.memory import open_memory
    from memsoc.triage import config, llm_client, triage_runner

    results, loaded = _checks(with_api=False, dry_run=dry_run, experiment=experiment)

    if not protocol_run._print_checks(log, results):
        log("Not starting: fix the FAIL lines above.", error=True)
        sys.exit(1)

    condition = EXPERIMENTS[experiment]["condition"]
    seed = EXPERIMENTS[experiment].get("seed_store")
    run_id = _run_id(experiment, dry_run)
    alerts, flows, start = _alerts(experiment, loaded, dry_run)
    verdicts_path = protocol_run._verdicts_path(run_id)

    _ensure_run_config(log, experiment, run_id, alerts, dry_run)
    _seed_memory(log, experiment, run_id)

    mem = open_memory(run_id, condition)
    done = triage_runner.load_done_rows(verdicts_path)
    by_uid = {a["uid"]: a for a in alerts}

    if seed:
        wanted = SEED_STORES[seed][0] + len(done)
        count = mem.collection.count()
        if count != wanted:
            log(f"ERROR: {run_id} store holds {count} cases, expected {wanted} "
                f"({SEED_STORES[seed][0]} seeded + {len(done)} written).", error=True)
            sys.exit(1)
        log(f"{run_id}: store holds {count} cases as expected")

    total = len(alerts)
    completed = len(done)
    log(f"{run_id}: {completed} of {total} verdicts already done; {total - completed} to go")

    calls = 0
    uid = "(resume replay)"

    try:

        # Rebuild memory from the verdicts already on disk. Writes are
        # idempotent, so a case that is already stored is a no-op.
        for row in sorted(done.values(), key=lambda r: r["seq"]):
            uid = row["uid"]
            triage_runner.write_back(mem, by_uid[uid], flows[uid], row)

        for seq, record in enumerate(alerts, start=start):

            uid = record["uid"]

            if uid in done:
                continue

            while True:

                if calls:
                    time.sleep(config.GEMINI_PACE_SECONDS)
                calls += 1

                try:
                    row = protocol_run._triage_with_retries(log, record, flows[uid], seq, mem, run_id)
                    break

                except llm_client.DailyBudgetExhausted as e:
                    if not wait_on_quota:
                        log(f"Daily quota reached: {str(e).splitlines()[0]}", error=True)
                        log("Run the same command again after the quota resets.", error=True)
                        sys.exit(2)
                    wait = protocol_run._quota_wait(e)
                    until = datetime.now() + timedelta(seconds=wait)
                    log(f"Daily quota reached. Waiting {wait / 60:.0f} min, until about "
                        f"{until:%H:%M}, then continuing automatically. Leave this window open.")
                    time.sleep(wait)

            row["protocol"] = PROTOCOL
            row["experiment"] = experiment

            # Benign only: the real detector figures beside the shown score.
            if "v4_benign" in record:
                row["v4_benign"] = record["v4_benign"]

            triage_runner.append_verdict(row, verdicts_path)
            triage_runner.write_back(mem, record, flows[uid], row)
            done[uid] = row
            completed += 1

            log(f"[{completed}/{total}] alert {seq - start + 1}/{total} {condition} "
                f"verdict={row['verdict']} category={row['attack_category']} "
                f"conf={row['confidence']} precedents={row['precedent_count']} "
                f"tokens={row.get('usage_total_tokens')} {row['latency_ms'] / 1000:.0f}s")

    except KeyboardInterrupt:
        log("Stopped by Ctrl-C. Everything written so far is kept; run the same command to continue.")
        sys.exit(130)

    except Exception as e:
        log(f"ERROR on alert {uid}: {type(e).__name__}: {str(e)[:1500]}", error=True)
        log("Everything written so far is kept. Run the same command to retry from here.", error=True)
        sys.exit(1)

    if getattr(mem, "skipped_writes", 0):
        log(f"WARNING: {mem.skipped_writes} memory writes failed -- report this to the team.", error=True)

    log(f"DONE: all {total} verdicts written. Next: run with --verify.")


# ----------------------------------------------------------------------
# Status, verify
# ----------------------------------------------------------------------

def _expected(experiment, dry_run):
    """(alert count, seq of the first alert) a finished run must have."""

    source = EXPERIMENTS[experiment]["alerts"]

    if source == "p3":
        total, start = protocol_run.PROTOCOL_ALERTS, 0
    else:
        from memsoc.triage import protocol_v4_benign
        manifest = json.loads(protocol_v4_benign.MANIFEST.read_text(encoding="utf-8"))
        total, start = manifest["sets"][source]["count"], protocol_run.PROTOCOL_ALERTS

    return (DRY_RUN_ALERTS if dry_run else total), start


def status(log, experiment, dry_run=False):

    from memsoc.triage import triage_runner

    run_id = _run_id(experiment, dry_run)
    rows = triage_runner.load_done_rows(protocol_run._verdicts_path(run_id))
    total, _ = _expected(experiment, dry_run)

    log(f"  {run_id:34} {len(rows):3} of {total} verdicts")


def _verify_shuffles(add, log, run_id, by_seq):
    """
    "shuffled" only. Every alert that retrieved precedent has a logged
    replacement for each retrieved case, a retried alert logged the same
    replacements each time, and the replacement labels are reported
    beside the store's own mix.
    """

    store_dir = Path(paths.memory_store(run_id))
    path = store_dir / "shuffles.jsonl"

    logged = {}
    consistent = True

    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                consistent &= logged.setdefault(row["uid"], row) == row

    wanted = {r["uid"]: r for r in by_seq.values() if r["precedent_count"]}

    matched = all(
        uid in logged
        and [x["case_id"] for x in logged[uid]["replacements"]] == [c for c in row["precedent_used"].split(",") if c]
        for uid, row in wanted.items()
    )

    add("every retrieved case's label replacement is logged", matched,
        f"{len(logged)} logged, {len(wanted)} alerts retrieved precedent")
    add("a retried alert got the same replacements", consistent)

    shown = Counter(x["to_attack_category"] for row in logged.values() for x in row["replacements"])
    stored = Counter()

    cases = store_dir / "cases.jsonl"
    if cases.exists():
        for line in cases.read_text(encoding="utf-8").splitlines():
            if line.strip():
                stored[json.loads(line)["metadata"]["attack_category"]] += 1

    log("")
    log("Label mix -- shown to the LLM after replacement vs stored (information, not a check):")
    for family in sorted(set(shown) | set(stored)):
        log(f"  {family:16} shown {shown[family]:4} ({shown[family] / max(sum(shown.values()), 1):6.1%})"
            f"   stored {stored[family]:4} ({stored[family] / max(sum(stored.values()), 1):6.1%})")


def verify(log, experiment, dry_run=False):

    from memsoc.triage import score_verdicts, triage_runner

    condition = EXPERIMENTS[experiment]["condition"]
    source = EXPERIMENTS[experiment]["alerts"]
    seed = EXPERIMENTS[experiment].get("seed_store")
    _, model_id, _ = protocol_run.MODELS[MODEL]
    run_id = _run_id(experiment, dry_run)
    total, start = _expected(experiment, dry_run)
    results = []

    def add(name, ok, detail="", warn=False):
        results.append((name, "PASS" if ok else ("WARN" if warn else "FAIL"), detail))

    verdicts_path = protocol_run._verdicts_path(run_id)
    by_seq = {r["seq"]: r for r in triage_runner.load_done_rows(verdicts_path).values()}

    add(f"{run_id}: {total} verdicts", sorted(by_seq) == list(range(start, start + total)),
        f"{len(by_seq)} found")
    add(f"{run_id}: one model", {r.get("model_id") for r in by_seq.values()} == {model_id},
        ", ".join(sorted({str(r.get('model_id')) for r in by_seq.values()})))

    config_path = Path(paths.run_dir(run_id)) / "run_config.json"
    recorded = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    add(f"{run_id}: run_config.json", bool(recorded))
    add("run_config is protocol v4", recorded.get("protocol") == PROTOCOL, str(recorded.get("protocol")))

    store = Path(paths.memory_store(run_id))

    if condition == "off":
        add("Arm A retrieved nothing", all(r["precedent_count"] == 0 for r in by_seq.values()))
        add("Arm A created no memory store", not store.exists())
    else:
        add("memory store exists", store.exists())

    if source == "p3":
        # Retrieval embeds the alert only, so every memory arm over these
        # alerts retrieves the same past alerts as the v3 reference.
        expected = protocol_run._load_expected_retrieval()
        seqs = [protocol_run._precedent_seqs(by_seq[s]) for s in sorted(by_seq)]
        differ = sum(1 for got, want in zip(seqs, expected) if got != want)
        add("retrieval matches the v3 reference", differ == 0,
            f"{differ} of {len(seqs)} alerts differ", warn=True)

    if seed and store.exists():
        from memsoc.memory import open_memory
        count = open_memory(run_id, condition).collection.count()
        add("store holds the seeded cases plus one per verdict",
            count == SEED_STORES[seed][0] + len(by_seq), f"{count} cases")

    if condition == "shuffled":
        _verify_shuffles(add, log, run_id, by_seq)

    log("")
    ok = protocol_run._print_checks(log, results)

    log("")
    log("Scores (memsoc.triage.score_verdicts, unchanged):")

    if source == "p3":
        out = subprocess.run(
            [sys.executable, "-m", "memsoc.triage.score_verdicts", "--verdicts", str(verdicts_path)],
            capture_output=True, text=True, cwd=paths.ROOT,
        )
        log(out.stdout.strip() or out.stderr.strip())

    else:
        # The benign flows are not in ground_truth.csv; they carry their
        # own. Same scoring functions, other truth file.
        from memsoc.triage import protocol_v4_benign

        verdicts = score_verdicts.read_verdicts(verdicts_path)
        truth = score_verdicts.read_ground_truth(protocol_v4_benign.set_paths(source)["ground_truth"])
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            score_verdicts.report(score_verdicts.score(verdicts, truth), verdicts[0]["arm"], False,
                                  score_verdicts.prompt_variants(verdicts)[0])
        log(buffer.getvalue().strip())

    return ok


# ----------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(description="MemSOC test protocol v4 -- supplementary, Gemma only")
    parser.add_argument("--experiment", required=True, choices=sorted(EXPERIMENTS))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true", help="check everything, make one API call, exit")
    mode.add_argument("--status", action="store_true", help="show progress and exit")
    mode.add_argument("--verify", action="store_true", help="check the finished run and print scores")
    parser.add_argument("--dry-run", action="store_true",
                        help=f"{DRY_RUN_ALERTS} real calls into a separate -dryrun run id; "
                             f"tag and note checks only warn")
    parser.add_argument("--no-wait", action="store_true",
                        help="exit with code 2 at a daily quota instead of waiting")
    args = parser.parse_args()

    protocol_run._load_env_file()
    protocol_run._select_model(MODEL)

    log = protocol_run.Log(Path(paths.RUNS_DIR) / f"protocol-{_run_id(args.experiment, args.dry_run)}.log")

    mode_name = ("preflight" if args.preflight else "status" if args.status
                 else "verify" if args.verify else "run")
    log(f"=== protocol {PROTOCOL} | experiment {args.experiment} | {mode_name}"
        f"{' | DRY RUN' if args.dry_run else ''} ===")

    if args.preflight:
        results, _ = _checks(with_api=True, dry_run=args.dry_run, experiment=args.experiment)
        sys.exit(0 if protocol_run._print_checks(log, results) else 1)

    if args.status:
        status(log, args.experiment, args.dry_run)
        return

    if args.verify:
        sys.exit(0 if verify(log, args.experiment, args.dry_run) else 1)

    run(log, args.experiment, wait_on_quota=not args.no_wait, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
