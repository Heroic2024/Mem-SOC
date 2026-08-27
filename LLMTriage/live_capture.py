"""
Stage 4 live capture.

Runs the EXISTING, UNMODIFIED detection API (final_ml_model_v1's
POST /api/logs) over the already-generated log stream
(log_generation/generated_logs.jsonl) and appends the model's full JSON
response for every flow to model_outputs/live_results.jsonl, one line
per flow, the moment each result comes back.

This is the ONLY Stage 4 component that talks to the detection API or
reads generated_logs.jsonl. generate_report.py never does either -- it
only reads whatever is currently in live_results.jsonl, so a report
always reflects the latest outputs the model has actually produced,
whether this script is still running or has already finished.

Usage:
    python live_capture.py                  # one pass through the stream, then exit
    python live_capture.py --loop            # wrap to the start and keep going forever
    python live_capture.py --interval 1.0    # pace one flow per second (sensor-like)
    python live_capture.py --reset           # start live_results.jsonl empty first
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import config

REPO_ROOT = Path(__file__).resolve().parents[1]
STREAM_PATH = REPO_ROOT / "log_generation" / "generated_logs.jsonl"


def append_result(path: Path, record: dict, outcome: dict) -> None:
    """
    Write one line: the identifying fields from the request plus the
    model's full, unmodified response. This is the entire hand-off
    format generate_report.py expects.
    """

    row = {
        "uid": record.get("uid"),
        "src_ip": record.get("id.orig_h"),
        "dst_ip": record.get("id.resp_h"),
        "proto_name": record.get("proto"),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "status": outcome.get("status"),
        "binary_confidence": (outcome.get("binary") or {}).get("confidence"),
        "multiclass": outcome.get("multiclass"),
        "alert": outcome.get("alert"),
    }

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def run_pass(stream_path: Path, api_url: str, out_path: Path, interval: float):

    count = 0
    written = 0

    with open(stream_path, "r", encoding="utf-8") as f:

        for line in f:

            if not line.strip():
                continue

            record = json.loads(line)
            count += 1

            try:
                response = requests.post(api_url, json=record, timeout=30)
            except requests.RequestException as e:
                print(f"[{record.get('uid', '?')}] request failed: {e}", file=sys.stderr)
                continue

            if response.status_code != 200:
                print(
                    f"[{record.get('uid', '?')}] HTTP {response.status_code}",
                    file=sys.stderr,
                )
                continue

            outcome = response.json()

            append_result(out_path, record, outcome)
            written += 1

            if outcome.get("status") == "attack":
                category = (outcome.get("multiclass") or {}).get("prediction")
                print(f"[{count}] uid={record.get('uid')} -> ATTACK/{category}")
            else:
                print(f"[{count}] uid={record.get('uid')} -> benign")

            if interval:
                time.sleep(interval)

    return count, written


def main():

    parser = argparse.ArgumentParser(description="Stage 4 live capture")
    parser.add_argument(
        "--loop", action="store_true",
        help="Wrap to the start of the stream and keep capturing forever"
    )
    parser.add_argument(
        "--interval", type=float, default=config.DEFAULT_CAPTURE_INTERVAL,
        help="Seconds to wait between flows (0 = as fast as the API allows)"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Start live_results.jsonl empty before capturing (explicit only -- "
             "this file is otherwise append-only across runs)"
    )
    args = parser.parse_args()

    out_path = config.LIVE_RESULTS_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.reset and out_path.exists():
        out_path.unlink()
        print(f"Reset: cleared {out_path}")

    if not STREAM_PATH.exists():
        print(f"Stream file not found: {STREAM_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Capturing model outputs from {config.DETECTION_API_URL}")
    print(f"Appending to {out_path}\n")

    wraps = 0

    try:
        while True:

            count, written = run_pass(
                STREAM_PATH, config.DETECTION_API_URL, out_path, args.interval
            )

            print(f"\nPass complete: {written}/{count} flows captured.")

            if not args.loop:
                break

            wraps += 1
            print(f"Looping (wrap {wraps}) ...\n")

    except KeyboardInterrupt:
        print("\nStopped by user.")


if __name__ == "__main__":
    main()
