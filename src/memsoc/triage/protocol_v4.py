"""
Test protocol v4 -- the supplementary memory experiments, Gemma only.

    python -m memsoc.triage.protocol_v4 --experiment <name> --preflight
    python -m memsoc.triage.protocol_v4 --experiment <name> --dry-run
    python -m memsoc.triage.protocol_v4 --experiment <name>
    python -m memsoc.triage.protocol_v4 --experiment <name> --status
    python -m memsoc.triage.protocol_v4 --experiment <name> --verify

<name> is a key of EXPERIMENTS. Each experiment is ONE memory arm run
over the same 165 alerts as protocol v3, and is compared against the
frozen v3 results (armA/bself/boracle-gemma4-26b-p3), which this module
never opens for writing. Those results stay the main experiment; every
run made here is supplementary.

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
import hashlib
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

# experiment -> (memory condition, run-id prefix). One arm per experiment.
EXPERIMENTS = {
    "shuffled": ("shuffled", "bshuf"),
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
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _run_id(experiment, dry_run=False):

    _, prefix = EXPERIMENTS[experiment]
    _, _, tag = protocol_run.MODELS[MODEL]

    return f"{prefix}-{tag}-{PROTOCOL}" + ("-dryrun" if dry_run else "")


def _alert_order_sha256(alerts):
    """SHA-256 of the uids joined by "\\n", in the order they are triaged."""

    return hashlib.sha256("\n".join(a["uid"] for a in alerts).encode()).hexdigest()


def _alerts(loaded, dry_run):

    first = loaded["first"]

    return first[:DRY_RUN_ALERTS] if dry_run else first


# ----------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------

def _checks(with_api, dry_run):
    """
    The v3 checks, with v3's tag check replaced by v4's, plus the
    pre-registration gate. Under --dry-run the tag, note and clean-tree
    checks warn instead of failing; every other check still fails.
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

    condition, _ = EXPERIMENTS[experiment]

    current = protocol_run._run_config(MODEL, run_id, condition)

    current.update({
        "protocol": PROTOCOL,
        "protocol_tag": PROTOCOL_TAG,
        "experiment": experiment,
        "dry_run": dry_run,
        "alerts": len(alerts),
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

    results, loaded = _checks(with_api=False, dry_run=dry_run)

    if not protocol_run._print_checks(log, results):
        log("Not starting: fix the FAIL lines above.", error=True)
        sys.exit(1)

    condition, _ = EXPERIMENTS[experiment]
    run_id = _run_id(experiment, dry_run)
    alerts, flows = _alerts(loaded, dry_run), loaded["flows"]
    verdicts_path = protocol_run._verdicts_path(run_id)

    _ensure_run_config(log, experiment, run_id, alerts, dry_run)

    mem = open_memory(run_id, condition)
    done = triage_runner.load_done_rows(verdicts_path)
    by_uid = {a["uid"]: a for a in alerts}

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

        for seq, record in enumerate(alerts):

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

            triage_runner.append_verdict(row, verdicts_path)
            triage_runner.write_back(mem, record, flows[uid], row)
            done[uid] = row
            completed += 1

            log(f"[{completed}/{total}] alert {seq + 1}/{total} {condition} "
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

def status(log, experiment, dry_run=False):

    from memsoc.triage import triage_runner

    run_id = _run_id(experiment, dry_run)
    rows = triage_runner.load_done_rows(protocol_run._verdicts_path(run_id))
    total = DRY_RUN_ALERTS if dry_run else protocol_run.PROTOCOL_ALERTS

    log(f"  {run_id:28} {len(rows):3} of {total} verdicts")


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

    from memsoc.triage import triage_runner

    condition, _ = EXPERIMENTS[experiment]
    _, model_id, _ = protocol_run.MODELS[MODEL]
    run_id = _run_id(experiment, dry_run)
    total = DRY_RUN_ALERTS if dry_run else protocol_run.PROTOCOL_ALERTS
    results = []

    def add(name, ok, detail="", warn=False):
        results.append((name, "PASS" if ok else ("WARN" if warn else "FAIL"), detail))

    verdicts_path = protocol_run._verdicts_path(run_id)
    by_seq = {r["seq"]: r for r in triage_runner.load_done_rows(verdicts_path).values()}

    add(f"{run_id}: {total} verdicts", sorted(by_seq) == list(range(total)), f"{len(by_seq)} found")
    add(f"{run_id}: one model", {r.get("model_id") for r in by_seq.values()} == {model_id},
        ", ".join(sorted({str(r.get('model_id')) for r in by_seq.values()})))

    config_path = Path(paths.run_dir(run_id)) / "run_config.json"
    recorded = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    add(f"{run_id}: run_config.json", bool(recorded))
    add("run_config is protocol v4", recorded.get("protocol") == PROTOCOL, str(recorded.get("protocol")))
    add("memory store exists", Path(paths.memory_store(run_id)).exists())

    # Retrieval embeds the alert only, so every memory arm over these
    # alerts retrieves the same past alerts as the v3 reference.
    expected = protocol_run._load_expected_retrieval()
    seqs = [protocol_run._precedent_seqs(by_seq[s]) for s in sorted(by_seq)]
    differ = sum(1 for got, want in zip(seqs, expected) if got != want)
    add("retrieval matches the v3 reference", differ == 0,
        f"{differ} of {len(seqs)} alerts differ", warn=True)

    if condition == "shuffled":
        _verify_shuffles(add, log, run_id, by_seq)

    log("")
    ok = protocol_run._print_checks(log, results)

    log("")
    log("Scores (memsoc.triage.score_verdicts, unchanged):")

    out = subprocess.run(
        [sys.executable, "-m", "memsoc.triage.score_verdicts", "--verdicts", str(verdicts_path)],
        capture_output=True, text=True, cwd=paths.ROOT,
    )
    log(out.stdout.strip() or out.stderr.strip())

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
        results, _ = _checks(with_api=True, dry_run=args.dry_run)
        sys.exit(0 if protocol_run._print_checks(log, results) else 1)

    if args.status:
        status(log, args.experiment, args.dry_run)
        return

    if args.verify:
        sys.exit(0 if verify(log, args.experiment, args.dry_run) else 1)

    run(log, args.experiment, wait_on_quota=not args.no_wait, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
