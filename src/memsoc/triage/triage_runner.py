"""
Phase 1 per-alert triage runner -- Arm A, the memoryless baseline.

Reads whatever live_capture.py has already written to
artifacts/model_outputs/live_results.jsonl, sends each detector-flagged
alert to the LLM on its own, and appends one validated verdict per alert
to artifacts/model_outputs/triage_verdicts.jsonl.

This module never calls the detection API -- running the model is
live_capture.py's job exclusively, the same separation generate_report.py
observes. It reads artifacts/generated_logs.jsonl for flow feature values
only; that file carries no Label or Attack column. It never reads
ground_truth.csv: verdicts are scored after the fact by
score_verdicts.py.

Arm A vs Arm B
--------------
This is Arm A. It writes nothing to a memory store and retrieves
nothing -- `precedent_used` is always "" and `precedent_count` always 0.

Phase 2 turns this into Arm B by inserting two steps into triage_alert()
below: a retrieval step before triage_prompt.render(), and a write-back
step after triage_prompt.parse_llm_response(). It does NOT add a second
codepath or an `if arm == ...` branch -- PROJECT_BRIEF.md section 9
requires the arms share everything except those two steps, so that any
measured difference is attributable to memory and not to incidental
implementation drift.

Usage (from the repo root, with src/ on PYTHONPATH):
    python -m memsoc.triage.triage_runner              # every untriaged alert
    python -m memsoc.triage.triage_runner --limit 5    # first 5 untriaged
    python -m memsoc.triage.triage_runner --dry-run    # one prompt, no call
"""

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import requests

from memsoc.triage import config
from memsoc.triage import llm_client
from memsoc.triage import stats_engine
from memsoc.triage import triage_prompt


def load_alerts():
    """
    Every detector-flagged alert, in stream order, one entry per uid.

    Deduplication is mandatory, not a nicety: live_capture.py --loop
    wraps back to the start of the stream and appends again, so
    live_results.jsonl currently holds more lines than there are
    distinct flows. Without this, alerts would be triaged -- and billed
    -- repeatedly, and the duplicates would then be double-counted in
    every metric.

    First occurrence wins, so ordering follows the first pass through
    the stream and is reproducible across runs.
    """

    results = stats_engine.read_live_results(config.LIVE_RESULTS_PATH)

    alerts = []
    seen = set()

    for record in results:

        uid = record.get("uid")

        if uid is None or uid in seen:
            continue

        if record.get("status") != "attack":
            continue

        if not record.get("alert") or not record.get("multiclass"):
            continue

        seen.add(uid)
        alerts.append(record)

    return alerts


def select_sample(alerts):
    """
    The stratified subsample of alerts to triage, as an ordered list.

    Read from the manifest if one exists, so every later run -- and
    Arm B -- triages exactly the same alerts. Otherwise chosen fresh
    from a fixed seed and written out.

    Selection is per detector category, capped at
    config.SAMPLE_PER_CATEGORY, with categories at or below the cap
    taken whole. Stream order is preserved in the result so `seq` and
    replay order stay meaningful.

    Any alert already triaged is forced into the sample regardless of
    the cap: excluding a verdict that has already been paid for and
    written would silently discard data.
    """

    if config.SAMPLE_MANIFEST_PATH.exists():

        with open(config.SAMPLE_MANIFEST_PATH, "r", encoding="utf-8") as f:
            chosen = set(json.load(f)["uids"])

        return [a for a in alerts if a["uid"] in chosen]

    by_category = defaultdict(list)

    for alert in alerts:
        by_category[alert["multiclass"]["prediction"]].append(alert["uid"])

    rng = random.Random(config.SAMPLE_SEED)
    chosen = set(load_done_uids())

    for category in sorted(by_category):

        uids = sorted(by_category[category])

        if len(uids) <= config.SAMPLE_PER_CATEGORY:
            chosen.update(uids)
        else:
            chosen.update(rng.sample(uids, config.SAMPLE_PER_CATEGORY))

    sample = [a for a in alerts if a["uid"] in chosen]

    config.SAMPLE_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(config.SAMPLE_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "seed": config.SAMPLE_SEED,
                "per_category_cap": config.SAMPLE_PER_CATEGORY,
                "total_alerts_available": len(alerts),
                "sample_size": len(sample),
                "uids": [a["uid"] for a in sample],
            },
            f,
            indent=2,
        )

    print(f"Wrote sample manifest: {config.SAMPLE_MANIFEST_PATH}")

    return sample


def load_flows():
    """
    The raw flow record for every uid in the stream, keyed by uid.

    live_results.jsonl carries the detector's output and its SHAP
    attributions but not the feature values those attributions refer to,
    and an attribution without its value is not evidence -- an earlier
    revision that omitted them drew "inconclusive" on every alert. This
    join supplies them.

    Read-only, and for feature values only. generated_logs.jsonl carries
    no Label or Attack column, so this introduces no oracle; ground
    truth remains confined to score_verdicts.py.
    """

    flows = {}

    with open(config.STREAM_PATH, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            uid = record.get("uid")

            if uid is not None:
                flows[uid] = record

    return flows


def load_done_uids():
    """
    uids already present in the verdicts file.

    This is what makes a run resumable. The check happens before the API
    call, so an interrupted run resumes at no request cost -- the single
    most valuable property of this script given the API budget.
    """

    if not config.VERDICTS_PATH.exists():
        return set()

    done = set()

    with open(config.VERDICTS_PATH, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            try:
                done.add(json.loads(line)["uid"])
            except (json.JSONDecodeError, KeyError):
                # A half-written trailing line from an interrupted run.
                # Skipping it means that one alert is retried, which is
                # correct: it was never durably recorded.
                continue

    return done


def triage_alert(record: dict, flow: dict, seq: int) -> dict:
    """
    Triage one alert and return the verdict row to be persisted.

    The two Phase 2 seams are marked below. Nothing else in this
    function changes when Arm B is built.
    """

    # -- Phase 2 seam: retrieve precedent from the memory store here. --

    prompt = triage_prompt.render(record, flow)

    raw_text, latency_ms = llm_client.call_groq(
        prompt,
        max_tokens=config.TRIAGE_MAX_RESPONSE_TOKENS,
        reasoning_effort=config.TRIAGE_REASONING_EFFORT,
    )

    verdict = triage_prompt.parse_llm_response(raw_text)

    # -- Phase 2 seam: write this case back to the memory store here. --

    multiclass = record["multiclass"]
    alert = record["alert"]

    return {
        "uid": record["uid"],
        "arm": "baseline",
        "seq": seq,
        "detector_label": multiclass["prediction"],
        "detector_score": multiclass["confidence"],
        "dst_port": alert["dst_port"],
        "protocol": alert["protocol"],
        "verdict": verdict["verdict"],
        "attack_category": verdict["attack_category"],
        "confidence": verdict["confidence"],
        "rationale_summary": verdict["rationale_summary"],
        # Arm A retrieves nothing and stores nothing. These stay empty
        # for every baseline row, by construction rather than by policy.
        "precedent_used": "",
        "precedent_count": 0,
        "model_id": config.GROQ_MODEL,
        "latency_ms": round(latency_ms, 1),
        "triaged_at": datetime.now(timezone.utc).isoformat(),
    }


def append_verdict(row: dict) -> None:
    """
    Append one verdict and flush immediately.

    Written per alert rather than batched at the end so that a crash,
    a rate-limit error, or a Ctrl-C costs at most one in-flight request
    instead of the whole run.
    """

    with open(config.VERDICTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def main():

    parser = argparse.ArgumentParser(
        description="Phase 1 per-alert triage (Arm A baseline)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Triage at most N alerts this run (default: all untriaged)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the prompt for the first pending alert and exit "
             "without calling the API"
    )
    args = parser.parse_args()

    if not config.LIVE_RESULTS_PATH.exists():
        print(
            f"No captured model outputs at {config.LIVE_RESULTS_PATH}.\n"
            "Run live_capture.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not config.STREAM_PATH.exists():
        print(f"Flow stream not found: {config.STREAM_PATH}", file=sys.stderr)
        sys.exit(1)

    alerts = load_alerts()

    if not alerts:
        print(
            f"{config.LIVE_RESULTS_PATH} contains no detector-flagged "
            "alerts yet.",
            file=sys.stderr,
        )
        sys.exit(1)

    flows = load_flows()

    # Refuse to run on a partial join rather than quietly triaging some
    # alerts without their measurements. A prompt missing the flow block
    # is a materially different prompt, and mixing the two kinds inside
    # one arm would put an uncontrolled variable into the comparison.
    missing = [a["uid"] for a in alerts if a["uid"] not in flows]

    if missing:
        print(
            f"{len(missing)} of {len(alerts)} alerts have no matching flow "
            f"in {config.STREAM_PATH}.\nFirst few: {missing[:5]}\n"
            "Every alert must join before triage can run.",
            file=sys.stderr,
        )
        sys.exit(1)

    sample = select_sample(alerts)

    done = load_done_uids()
    pending = [a for a in sample if a["uid"] not in done]

    print(f"{len(alerts)} alerts available, {len(sample)} in sample, "
          f"{len(done)} already triaged, {len(pending)} pending")

    remaining_budget = llm_client.budget_remaining()
    print(f"Daily request budget remaining: {remaining_budget}")

    if remaining_budget < len(pending):
        print(
            f"WARNING: {len(pending)} alerts pending but only "
            f"{remaining_budget} requests left today, and retries cost "
            "extra.\n         The run will stop cleanly at the cap and "
            "resume after UTC midnight.",
            file=sys.stderr,
        )

    if args.dry_run:

        if not pending:
            print("Nothing pending -- no prompt to show.")
            return

        print("\n" + "=" * 70)
        print(triage_prompt.render(pending[0], flows[pending[0]["uid"]]))
        print("=" * 70)
        print("\nDry run: no API call was made.")
        return

    if not pending:
        print("Nothing to do -- every alert already has a verdict.")
        return

    if args.limit is not None:
        pending = pending[: args.limit]
        print(f"Limited to {len(pending)} this run")

    config.VERDICTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # seq is the alert's position in the full stream, not in this batch,
    # so it stays stable across resumed runs.
    position = {a["uid"]: i for i, a in enumerate(alerts)}

    written = 0
    agreed = 0

    try:
        for index, record in enumerate(pending):

            uid = record["uid"]

            # Pace before every call except the first. The tokens-per-
            # minute quota forces roughly one call a minute regardless;
            # waiting deliberately costs the same wall-clock time as
            # being rejected, but does not spend a request from the
            # daily budget to learn that.
            if index:
                time.sleep(config.TRIAGE_PACE_SECONDS)

            try:
                row = triage_alert(record, flows[uid], position[uid])
            except llm_client.DailyBudgetExhausted as e:
                print(f"\n{e}", file=sys.stderr)
                print(
                    f"Stopped after {written} verdicts this run.",
                    file=sys.stderr,
                )
                sys.exit(2)
            except (ValueError, requests.RequestException) as e:
                # Stop rather than skip. A systematic cause -- a rate
                # limit, a revoked key, a model that stopped honouring
                # the JSON instruction -- would otherwise burn the
                # remaining budget producing nothing. Everything written
                # so far is durable, and rerunning resumes here.
                print(f"\n[{uid}] triage failed: {e}", file=sys.stderr)
                print(
                    f"Stopped after {written} verdicts. Fix the cause and "
                    "rerun -- completed alerts will be skipped.",
                    file=sys.stderr,
                )
                sys.exit(1)

            append_verdict(row)
            written += 1

            if row["attack_category"] == row["detector_label"]:
                agreed += 1

            flag = "=" if row["attack_category"] == row["detector_label"] else "~"

            print(
                f"[{written}/{len(pending)}] {uid} "
                f"detector={row['detector_label']} {flag} "
                f"llm={row['attack_category']} "
                f"verdict={row['verdict']} conf={row['confidence']}"
            )

    except KeyboardInterrupt:
        print(f"\nStopped by user after {written} verdicts.", file=sys.stderr)
        sys.exit(130)

    print(f"\nWrote {written} verdicts to {config.VERDICTS_PATH}")

    if written:
        rate = agreed / written
        print(f"Agreement with detector this run: {agreed}/{written} "
              f"({rate:.1%})")
        if rate == 1.0:
            print(
                "\nWARNING: the LLM echoed the detector's category on every "
                "alert.\nIf this holds over the full run, category accuracy "
                "measures nothing --\nboth arms would tie at the detector's "
                "own 88.1%. Review the prompt in\ntriage_prompt.py before "
                "spending the rest of the request budget."
            )

    print("Score with: python -m memsoc.triage.score_verdicts")


if __name__ == "__main__":
    main()
