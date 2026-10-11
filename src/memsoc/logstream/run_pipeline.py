"""
MemSOC end-to-end pipeline runner -- one command, generation to verdict.

Wires the three existing stages together and manages the API process so a
demo is a single command instead of three terminals:

    stage 1  generate   NF-UNSW-NB15-v3.csv -> generated_logs.jsonl
                                            -> ground_truth.csv
    stage 2  serve      start uvicorn, wait for /health
    stage 3  classify   POST each flow -> /api/logs -> verdict
    stage 4  report     status codes, verdict distribution, timings

Nothing here reimplements a stage. Generation, replay and streaming all
come from the existing modules; this file only sequences them, overriding
their module-level config for the requested run size. That keeps a single
source of truth for the 48-feature contract and the seeded ordering.

Every path comes from paths.py at the repo root, so this runs the same
from any working directory and inside the container. Override the dataset
or model location with MEMSOC_DATASET_CSV / MEMSOC_MODELS_DIR rather than
editing anything here.

Usage:
    python run_pipeline.py                     # batch demo, 100 flows
    python run_pipeline.py --flows 500
    python run_pipeline.py --mode stream       # live sensor, Ctrl+C to stop
    python run_pipeline.py --regenerate        # rebuild the log from the CSV
    python run_pipeline.py --no-api            # use an API already running
"""

import argparse
import os
import subprocess
import sys
import time
from collections import Counter

import requests

from memsoc import paths
from memsoc.logstream import nfv3_log_generator as generator
from memsoc.logstream import replay_to_api as replayer

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------
API_BASE = paths.API_BASE
API_HEALTH = paths.API_HEALTH
API_LOG = paths.API_SERVER_LOG

STARTUP_TIMEOUT = 180   # multiclass model is ~37MB; first load is slow
POLL_INTERVAL = 1.0

REQUIRED_MODELS = [paths.BINARY_MODEL, paths.MULTICLASS_MODEL]


# ---------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------
def banner(text: str) -> None:
    print(f"\n{'=' * 62}")
    print(f"  {text}")
    print(f"{'=' * 62}\n")


def step(text: str) -> None:
    print(f"  -> {text}")


def bar(count: int, total: int, width: int = 28) -> str:
    filled = 0 if total == 0 else round(width * count / total)
    return "#" * filled + "." * (width - filled)


# ---------------------------------------------------------------------
# STAGE 0: preflight
# ---------------------------------------------------------------------
def preflight(need_dataset: bool) -> None:
    banner("STAGE 0 / PREFLIGHT")

    problems = []

    for path in REQUIRED_MODELS:
        if os.path.exists(path):
            size = os.path.getsize(path) / 1_048_576
            step(f"model  {os.path.basename(path):<26} {size:6.1f} MB")
        else:
            problems.append(f"missing model: {path}")

    if need_dataset:
        if os.path.exists(generator.INPUT_CSV):
            size = os.path.getsize(generator.INPUT_CSV) / 1_073_741_824
            step(f"data   NF-UNSW-NB15-v3.csv        {size:6.2f} GB")
        else:
            problems.append(f"missing dataset: {generator.INPUT_CSV}")
    else:
        if os.path.exists(generator.OUTPUT_JSONL):
            with open(generator.OUTPUT_JSONL, encoding="utf-8") as f:
                lines = sum(1 for _ in f)
            name = os.path.basename(generator.OUTPUT_JSONL)
            step(f"logs   {name:<26} {lines:6,} records")
        else:
            problems.append(
                f"{generator.OUTPUT_JSONL} not found -- run with --regenerate"
            )

    if problems:
        print()
        for problem in problems:
            print(f"  FAIL: {problem}")
        raise SystemExit(1)

    step("preflight OK")


# ---------------------------------------------------------------------
# STAGE 1: generation
# ---------------------------------------------------------------------
def generate(flows: int) -> None:
    banner("STAGE 1 / LOG GENERATION")

    # The generator reads SAMPLE_SIZE at call time, so overriding the
    # module constant reuses it as-is rather than forking its logic.
    generator.SAMPLE_SIZE = flows

    started = time.time()
    generator.main()

    print(f"\n  generation took {time.time() - started:.1f}s")


# ---------------------------------------------------------------------
# STAGE 2: API lifecycle
# ---------------------------------------------------------------------
def api_is_up() -> bool:
    try:
        response = requests.get(API_HEALTH, timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


def start_api():
    banner("STAGE 2 / INFERENCE API")

    if api_is_up():
        step(f"API already healthy at {API_BASE} -- reusing it")
        return None

    env = dict(os.environ)

    # src/ on the path so the `memsoc` package imports. One entry now --
    # this used to need final_ml_model_v1/ for `src.api.server` plus the
    # repo root for `paths`, because the two lived in different trees.
    env["PYTHONPATH"] = os.pathsep.join(
        [paths.SRC_DIR, env.get("PYTHONPATH", "")]
    )

    paths.ensure_dirs()

    log_handle = open(API_LOG, "w", encoding="utf-8")

    step("launching uvicorn (memsoc.api.app_detection:app)")

    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "memsoc.api.app_detection:app",
            "--host", paths.API_BIND, "--port", str(paths.API_PORT),
        ],
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    process._memsoc_log = log_handle   # keep the handle alive for teardown

    step(f"pid {process.pid}, output -> {os.path.basename(API_LOG)}")
    step("waiting for models to load...")

    deadline = time.time() + STARTUP_TIMEOUT

    while time.time() < deadline:

        if process.poll() is not None:
            stop_api(process)
            print(f"\n  FAIL: uvicorn exited early (code {process.returncode}).")
            print(f"  See {API_LOG} for the traceback.")
            raise SystemExit(1)

        if api_is_up():
            waited = STARTUP_TIMEOUT - (deadline - time.time())
            step(f"healthy after {waited:.1f}s")
            return process

        time.sleep(POLL_INTERVAL)

    stop_api(process)
    print(f"\n  FAIL: API did not become healthy within {STARTUP_TIMEOUT}s.")
    raise SystemExit(1)


def stop_api(process) -> None:
    if process is None:
        return

    step("stopping API")

    process.terminate()

    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)

    handle = getattr(process, "_memsoc_log", None)
    if handle is not None:
        handle.close()


# ---------------------------------------------------------------------
# STAGE 3: classification
# ---------------------------------------------------------------------
def classify(flows: int, delay: float) -> dict:
    """
    Replay the generated log through the API.

    Reuses the replayer's loader and its response formatter, so the
    response shape is understood in exactly one place. Verdict counts are
    tallied here for the demo summary -- this is descriptive only, not
    scoring against ground truth, which belongs to the frozen harness.
    """

    banner("STAGE 3 / CLASSIFICATION")

    records = replayer.load_records(generator.OUTPUT_JSONL, flows)
    total = len(records)

    print(f"  source : {generator.OUTPUT_JSONL}")
    print(f"  target : {replayer.API_URL}")
    print(f"  flows  : {total:,}\n")

    statuses = Counter()
    verdicts = Counter()
    categories = Counter()
    failures = []
    latencies = []

    started = time.time()

    for i, record in enumerate(records, start=1):
        uid = record.get("uid", "?")

        sent = time.time()

        try:
            response = requests.post(replayer.API_URL, json=record, timeout=30)
        except requests.RequestException as e:
            statuses["error"] += 1
            failures.append((uid, str(e)))
            print(f"  [{i}/{total}] uid={uid} REQUEST FAILED: {e}")
            continue

        latencies.append((time.time() - sent) * 1000)
        statuses[response.status_code] += 1

        if response.status_code == 200:
            result = response.json()

            binary = (result.get("binary") or {}).get("prediction", "?")
            verdicts[binary] += 1

            multi = result.get("multiclass") or {}
            if multi:
                categories[multi.get("prediction", "?")] += 1

            print(f"  [{i}/{total}] uid={uid} HTTP 200 -> "
                  f"{replayer.describe(result)}")
        else:
            detail = response.text[:160]
            failures.append((uid, f"HTTP {response.status_code}: {detail}"))
            print(f"  [{i}/{total}] uid={uid} HTTP "
                  f"{response.status_code} -> {detail}")

        if delay:
            time.sleep(delay)

    return {
        "total": total,
        "statuses": statuses,
        "verdicts": verdicts,
        "categories": categories,
        "failures": failures,
        "latencies": latencies,
        "elapsed": time.time() - started,
    }


# ---------------------------------------------------------------------
# STAGE 4: report
# ---------------------------------------------------------------------
def report(results: dict) -> int:
    banner("STAGE 4 / RESULTS")

    total = results["total"]
    accepted = results["statuses"].get(200, 0)

    print("  HTTP status")
    for status, count in sorted(results["statuses"].items(), key=lambda kv: str(kv[0])):
        print(f"    {str(status):<10} {count:>6,}")

    print(f"\n  Accepted   {accepted:,}/{total:,} "
          f"({0 if total == 0 else accepted / total:.1%})")

    if results["latencies"]:
        latencies = sorted(results["latencies"])
        mean = sum(latencies) / len(latencies)
        p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        print(f"  Latency    mean {mean:6.1f} ms   p95 {p95:6.1f} ms")

    print(f"  Wall clock {results['elapsed']:.1f}s\n")

    if results["verdicts"]:
        print("  Verdict distribution")
        for verdict, count in results["verdicts"].most_common():
            print(f"    {verdict:<14} {count:>6,}  {bar(count, accepted)}")

    if results["categories"]:
        attacks = sum(results["categories"].values())
        print("\n  Attack categories")
        for category, count in results["categories"].most_common():
            print(f"    {category:<14} {count:>6,}  {bar(count, attacks)}")

    if results["failures"]:
        print(f"\n  First {min(5, len(results['failures']))} failures")
        for uid, reason in results["failures"][:5]:
            print(f"    uid={uid} -> {reason}")

    ok = total > 0 and accepted == total

    print()
    print("  RESULT: PIPELINE OK -- every flow classified"
          if ok else "  RESULT: PIPELINE DEGRADED -- see failures above")

    # Ground truth is never scored here; it stays the evaluation oracle.
    if os.path.exists(generator.GROUND_TRUTH_CSV):
        print(f"  Ground truth held out in {generator.GROUND_TRUTH_CSV} "
              f"(not scored -- evaluation harness only)")

    return 0 if ok else 1


# ---------------------------------------------------------------------
# Stream mode
# ---------------------------------------------------------------------
def run_stream(interval: float, flows) -> int:
    banner("STAGE 3 / CONTINUOUS STREAM")

    from memsoc.logstream import stream_to_api as streamer

    streamer.FLOW_INTERVAL = interval

    # streamer.MAX_FLOWS is a LIFETIME cap against the resumable cursor,
    # but --flows here means "emit this many now". Offset by what the
    # cursor has already emitted so a demo run is not a no-op on a warm
    # cursor. Unbounded leaves it as None.
    already = streamer.load_state()["emitted"] if flows else 0

    streamer.MAX_FLOWS = None if flows is None else already + flows

    print(f"  interval : {interval}s per flow")
    print(f"  emitting : {flows if flows else 'unbounded (Ctrl+C to stop)'}")
    print(f"  cursor   : {streamer.STATE_FILE} (already emitted {already:,})\n")

    streamer.main()

    return 0


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the MemSOC pipeline end to end."
    )
    parser.add_argument(
        "--mode", choices=["batch", "stream"], default="batch",
        help="batch: replay a fixed sample. stream: live sensor emulation.",
    )
    parser.add_argument(
        "--flows", type=int, default=100,
        help="flows to classify (batch), or to emit before stopping (stream).",
    )
    parser.add_argument(
        "--unbounded", action="store_true",
        help="stream mode: run until Ctrl+C instead of stopping at --flows.",
    )
    parser.add_argument(
        "--regenerate", action="store_true",
        help="rebuild generated_logs.jsonl from the CSV (slow: full scan).",
    )
    parser.add_argument(
        "--sample-size", type=int, default=generator.SAMPLE_SIZE,
        help="records to write when regenerating.",
    )
    parser.add_argument(
        "--delay", type=float, default=0.0,
        help="seconds between requests in batch mode.",
    )
    parser.add_argument(
        "--no-api", action="store_true",
        help="do not start uvicorn; assume an API is already running.",
    )
    parser.add_argument(
        "--paths", action="store_true",
        help="print the resolved path layout and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.paths:
        banner("RESOLVED PATHS")
        print(paths.describe())
        print()
        return 0

    banner("MemSOC  --  NF-UNSW-NB15 FLOW TRIAGE PIPELINE")
    print(f"  mode  : {args.mode}")
    print(f"  seed  : {generator.SEED} (deterministic order)")
    print(f"  model : LightGBM binary + multiclass, 48 NetFlow features")
    print(f"  root  : {paths.ROOT}")

    # Stream mode reads the CSV directly and never touches the JSONL.
    needs_dataset = args.regenerate or args.mode == "stream"

    preflight(needs_dataset)

    if args.regenerate:
        generate(args.sample_size)

    process = None

    try:
        if not args.no_api:
            process = start_api()
        elif not api_is_up():
            print(f"\n  FAIL: --no-api given but nothing healthy at {API_BASE}")
            return 1

        if args.mode == "stream":
            return run_stream(
                args.delay or 1.0,
                None if args.unbounded else args.flows,
            )

        results = classify(args.flows, args.delay)
        return report(results)

    except KeyboardInterrupt:
        print("\n\n  interrupted")
        return 130

    finally:
        stop_api(process)
        print()


if __name__ == "__main__":
    sys.exit(main())
