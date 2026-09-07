"""
Stage 4 live capture.

Runs the EXISTING detection API (final_ml_model_v1's POST /api/logs) over
the generated log stream and appends the model's full JSON response for
every flow to model_outputs/live_results.jsonl.

The generated log location can be overridden using MEMSOC_ARTIFACTS_DIR.
This allows the same script to work both locally and inside Docker.

Usage:
    python live_capture.py
    python live_capture.py --loop
    python live_capture.py --interval 1.0
    python live_capture.py --reset
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import config

REPO_ROOT = Path(__file__).resolve().parents[1]

STREAM_PATH = Path(
    os.environ.get(
        "MEMSOC_ARTIFACTS_DIR",
        str(REPO_ROOT / "log_generation")
    )
) / "generated_logs.jsonl"


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
        "binary_confidence": (
            outcome.get("binary") or {}
        ).get("confidence"),
        "multiclass": outcome.get("multiclass"),
        "alert": outcome.get("alert"),
    }

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def run_pass(
    stream_path: Path,
    api_url: str,
    out_path: Path,
    interval: float
):

    count = 0
    written = 0

    with open(stream_path, "r", encoding="utf-8") as f:

        for line in f:

            if not line.strip():
                continue

            record = json.loads(line)
            count += 1

            try:
                response = requests.post(
                    api_url,
                    json=record,
                    timeout=30
                )

            except requests.RequestException as e:
                print(
                    f"[{record.get('uid', '?')}] "
                    f"request failed: {e}",
                    file=sys.stderr
                )
                continue

            if response.status_code != 200:
                print(
                    f"[{record.get('uid', '?')}] "
                    f"HTTP {response.status_code}",
                    file=sys.stderr
                )
                continue

            outcome = response.json()

            append_result(
                out_path,
                record,
                outcome
            )

            written += 1

            if outcome.get("status") == "attack":

                category = (
                    outcome.get("multiclass") or {}
                ).get("prediction")

                print(
                    f"[{count}] "
                    f"uid={record.get('uid')} "
                    f"-> ATTACK/{category}"
                )

            else:

                print(
                    f"[{count}] "
                    f"uid={record.get('uid')} "
                    f"-> benign"
                )

            if interval:
                time.sleep(interval)

    return count, written


def main():

    parser = argparse.ArgumentParser(
        description="Stage 4 live capture"
    )

    parser.add_argument(
        "--loop",
        action="store_true",
        help="Wrap to the start of the stream and keep capturing forever"
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=config.DEFAULT_CAPTURE_INTERVAL,
        help="Seconds to wait between flows (0 = as fast as the API allows)"
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Start live_results.jsonl empty before capturing "
            "(explicit only -- this file is otherwise append-only across runs)"
        )
    )

    args = parser.parse_args()

    out_path = config.LIVE_RESULTS_PATH

    out_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if args.reset and out_path.exists():

        out_path.unlink()

        print(
            f"Reset: cleared {out_path}"
        )

    if not STREAM_PATH.exists():

        print(
            f"Stream file not found: {STREAM_PATH}",
            file=sys.stderr
        )

        sys.exit(1)

    print(
        f"Capturing model outputs from "
        f"{config.DETECTION_API_URL}"
    )

    print(
        f"Reading generated logs from {STREAM_PATH}"
    )

    print(
        f"Appending to {out_path}\n"
    )

    wraps = 0

    try:

        while True:

            count, written = run_pass(
                STREAM_PATH,
                config.DETECTION_API_URL,
                out_path,
                args.interval
            )

            print(
                f"\nPass complete: "
                f"{written}/{count} flows captured."
            )

            if not args.loop:
                break

            wraps += 1

            print(
                f"Looping (wrap {wraps}) ...\n"
            )

    except KeyboardInterrupt:

        print(
            "\nStopped by user."
        )


if __name__ == "__main__":
    main()