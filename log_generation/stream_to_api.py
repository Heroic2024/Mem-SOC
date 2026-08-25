"""
Continuous NF-UNSW-NB15 flow stream -> MemSOC inference API.

Behaves like a live sensor: emits one flow every FLOW_INTERVAL seconds,
POSTs it to /api/logs, appends it to a stream log, and keeps going
indefinitely -- wrapping back to the start when the dataset is exhausted.

Determinism (required by CLAUDE.md):
    The emission order is a seeded permutation of the eligible rows,
    derived from SEED rather than stored. stream_state.json records how
    far along that fixed sequence the stream has walked, so killing and
    restarting resumes the same sequence at the same point.

Random access:
    A one-time byte-offset index (stream_index.npy) records where every
    eligible row starts in the CSV, so fetching flow N is a seek() plus
    a readline() -- no rescan, no growth in memory.

Prerequisite -- start the API (see README for the cwd/PYTHONPATH note):
    python -m uvicorn src.api.server:app

Usage:
    python stream_to_api.py            # stream until Ctrl+C
"""

import csv
import json
import math
import os
import time
from collections import Counter

import numpy as np
import requests

from nfv3_log_generator import (
    INPUT_CSV,
    SEED,
    build_record,
    read_feature_columns,
    validate_record,
)
from replay_to_api import describe

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------
API_URL = "http://127.0.0.1:8000/api/logs"

FLOW_INTERVAL = 0.5    # seconds between flows
MAX_FLOWS = None       # set to an int to stop after N flows

INDEX_FILE = "stream_index.npy"
STATE_FILE = "stream_state.json"
STREAM_LOG = "stream_log.jsonl"
STREAM_GROUND_TRUTH = "stream_ground_truth.csv"


# ---------------------------------------------------------------------
# Row parsing
# ---------------------------------------------------------------------
def to_number(value: str):
    """CSV cells arrive as text; give back native numbers where possible."""

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        return value


def parse_row(columns: list, line: str) -> dict:

    values = next(csv.reader([line]))

    return {
        column: to_number(value)
        for column, value in zip(columns, values)
    }


def is_eligible(row: dict, feature_columns: list) -> bool:
    """
    Every feature finite and numeric -- the same rule the inference
    pipeline enforces, so nothing that would return HTTP 400 is emitted.
    """

    for column in feature_columns:

        value = row[column]

        if not isinstance(value, (int, float)):
            return False

        if isinstance(value, float) and not math.isfinite(value):
            return False

    return True


# ---------------------------------------------------------------------
# Byte-offset index
# ---------------------------------------------------------------------
def read_header(path: str) -> list:

    with open(path, "r", encoding="utf-8", newline="") as f:
        return [c.strip() for c in next(csv.reader([f.readline()]))]


def build_index(path: str, columns: list, feature_columns: list) -> np.ndarray:
    """
    One pass over the CSV recording the byte offset of every eligible row.

    Uses explicit readline() rather than iterating the file object, since
    tell() is not usable mid-iteration.
    """

    print("Building stream index (one-time, a few minutes)...")

    offsets = []
    scanned = 0

    with open(path, "r", encoding="utf-8", newline="") as f:

        f.readline()  # header

        while True:

            offset = f.tell()
            line = f.readline()

            if not line:
                break

            scanned += 1

            if is_eligible(parse_row(columns, line), feature_columns):
                offsets.append(offset)

            if scanned % 200_000 == 0:
                print(
                    f"[index] {scanned:,} rows scanned "
                    f"-- {len(offsets):,} eligible"
                )

    index = np.array(offsets, dtype=np.int64)

    np.save(INDEX_FILE, index)

    excluded = scanned - len(index)

    print(f"\n[index] {scanned:,} rows scanned")
    print(
        f"[index] {excluded:,} excluded "
        f"({excluded / scanned:.2%}) -- non-finite feature values"
    )
    print(f"[index] {len(index):,} eligible -> {INDEX_FILE}\n")

    return index


def load_index(path: str, columns: list, feature_columns: list) -> np.ndarray:

    if os.path.exists(INDEX_FILE):
        index = np.load(INDEX_FILE)
        print(f"Loaded index: {len(index):,} eligible rows\n")
        return index

    return build_index(path, columns, feature_columns)


# ---------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------
def load_state() -> dict:

    fresh = {"seed": SEED, "position": 0, "emitted": 0, "wraps": 0}

    if not os.path.exists(STATE_FILE):
        return fresh

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    # Splicing two different seeded sequences together would silently
    # destroy reproducibility, so refuse rather than guess.
    if state.get("seed") != SEED:
        raise SystemExit(
            f"{STATE_FILE} was written with seed {state.get('seed')}, "
            f"but SEED is now {SEED}.\n"
            f"Delete {STATE_FILE} to start a new stream, "
            f"or restore the original seed to resume."
        )

    return state


def save_state(state: dict) -> None:

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------
def print_summary(state: dict, statuses: Counter, benign: int, attack: int):

    print("\n\n========== STREAM SUMMARY ==========\n")
    print(f"Flows emitted : {state['emitted']:,}")
    print(f"Position      : {state['position']:,}")
    print(f"Wraps         : {state['wraps']}")
    print(f"Benign/Attack : {benign:,} / {attack:,}  (ground truth)")

    if statuses:
        print("\nResponses:")
        for status, count in sorted(
            statuses.items(), key=lambda kv: str(kv[0])
        ):
            print(f"  {status}: {count:,}")

    print(f"\nState saved to {STATE_FILE} -- rerun to resume.")


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def main():

    print("\n========== CONTINUOUS FLOW STREAM ==========\n")

    columns = read_header(INPUT_CSV)
    feature_columns = read_feature_columns(INPUT_CSV)

    index = load_index(INPUT_CSV, columns, feature_columns)

    # Derived, never stored: same SEED -> same sequence, always.
    order = np.random.default_rng(SEED).permutation(len(index))

    state = load_state()

    ground_truth_exists = os.path.exists(STREAM_GROUND_TRUTH)

    print(f"Target   : {API_URL}")
    print(f"Seed     : {SEED}")
    print(f"Interval : {FLOW_INTERVAL}s")
    print(
        f"Resuming : position {state['position']:,} "
        f"(emitted {state['emitted']:,})\n"
    )

    statuses = Counter()
    benign = 0
    attack = 0

    source = open(INPUT_CSV, "r", encoding="utf-8", newline="")

    log_f = open(STREAM_LOG, "a", encoding="utf-8")
    gt_f = open(STREAM_GROUND_TRUTH, "a", encoding="utf-8", newline="")

    if not ground_truth_exists:
        gt_f.write("uid,label,attack\n")

    try:
        while MAX_FLOWS is None or state["emitted"] < MAX_FLOWS:

            source.seek(int(index[order[state["position"]]]))
            row = parse_row(columns, source.readline())

            seq = state["emitted"] + 1

            record = build_record(row, seq, feature_columns)
            validate_record(record, feature_columns, seq)

            log_f.write(json.dumps(record) + "\n")
            log_f.flush()

            label = int(row["Label"])
            gt_f.write(f"{record['uid']},{label},{row['Attack']}\n")
            gt_f.flush()

            if label == 1:
                attack += 1
            else:
                benign += 1

            try:
                response = requests.post(API_URL, json=record, timeout=30)

                statuses[response.status_code] += 1

                if response.status_code == 200:
                    verdict = describe(response.json())
                else:
                    verdict = f"REJECTED {response.text[:120]}"

                print(
                    f"[{seq}] uid={record['uid']} "
                    f"HTTP {response.status_code} -> {verdict}"
                )

            except requests.RequestException as e:
                # A restarting API must not kill a long soak.
                statuses["error"] += 1
                print(f"[{seq}] uid={record['uid']} REQUEST FAILED: {e}")

            state["emitted"] = seq
            state["position"] += 1

            if state["position"] >= len(order):
                state["position"] = 0
                state["wraps"] += 1
                print(
                    f"\n--- dataset exhausted, wrapping "
                    f"(wrap {state['wraps']}) ---\n"
                )

            save_state(state)

            if FLOW_INTERVAL:
                time.sleep(FLOW_INTERVAL)

    except KeyboardInterrupt:
        print("\n\nStopped by user.")

    finally:
        save_state(state)
        source.close()
        log_f.close()
        gt_f.close()

    print_summary(state, statuses, benign, attack)


if __name__ == "__main__":
    main()
