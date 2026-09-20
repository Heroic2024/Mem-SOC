"""
Replay generated_logs.jsonl into the MemSOC inference API.

Reads the JSONL stream in order and POSTs each record to /api/logs,
reporting the HTTP status and the verdict the pipeline returned.

This script proves ACCEPTANCE -- that the generated logs satisfy the
48-feature contract and the pipeline runs end to end on them. It does
not score predictions against ground truth; metric definitions belong
to the evaluation harness, not here.

Prerequisite -- start the API from final_ml_model_v1/:
    python -m uvicorn src.api.server:app

Usage:
    python replay_to_api.py
"""

import json
import os
import sys
import time
from collections import Counter

import requests

from memsoc import paths

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------
INPUT_JSONL = paths.GENERATED_LOGS
API_URL = paths.API_URL
DELAY = 0.1        # seconds between requests
LIMIT = None       # set to an int to replay only the first N records


def load_records(path: str, limit=None) -> list:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            records.append(json.loads(line))
            if limit is not None and len(records) >= limit:
                break
    return records


def describe(result: dict) -> str:
    """
    One-line summary of the pipeline response.

    Shape (see InferencePipeline.predict):
        {"status", "binary": {...}, "multiclass": {...}|None,
         "shap": [...]|None, "alert": {...}|None}
    """

    binary = result.get("binary") or {}
    multi = result.get("multiclass") or {}

    verdict = binary.get("prediction", "?")
    confidence = binary.get("confidence")

    # Attack path: report the attack category and its confidence.
    if multi:
        verdict = f"{verdict}/{multi.get('prediction', '?')}"
        confidence = multi.get("confidence", confidence)

    extras = []
    if result.get("shap"):
        extras.append("shap")
    if result.get("alert"):
        extras.append("alert")

    line = verdict
    if isinstance(confidence, (int, float)):
        line += f" ({confidence:.3f})"
    if extras:
        line += " +" + "+".join(extras)

    return line


def main():
    records = load_records(INPUT_JSONL, LIMIT)
    total = len(records)

    print("\n========== REPLAY -> MEMSOC API ==========\n")
    print(f"Source : {INPUT_JSONL}")
    print(f"Target : {API_URL}")
    print(f"Records: {total:,}\n")

    statuses = Counter()
    failures = []

    for i, record in enumerate(records, start=1):
        uid = record.get("uid", "?")

        try:
            response = requests.post(API_URL, json=record, timeout=30)
        except requests.RequestException as e:
            statuses["error"] += 1
            failures.append((uid, str(e)))
            print(f"[{i}/{total}] uid={uid} REQUEST FAILED: {e}")
            continue

        statuses[response.status_code] += 1

        if response.status_code == 200:
            print(f"[{i}/{total}] uid={uid} HTTP 200 -> "
                  f"{describe(response.json())}")
        else:
            detail = response.text[:200]
            failures.append((uid, f"HTTP {response.status_code}: {detail}"))
            print(f"[{i}/{total}] uid={uid} HTTP "
                  f"{response.status_code} -> {detail}")

        if DELAY:
            time.sleep(DELAY)

    print("\n========== SUMMARY ==========\n")
    for status, count in sorted(statuses.items(), key=lambda kv: str(kv[0])):
        print(f"  {status}: {count:,}")

    accepted = statuses.get(200, 0)
    print(f"\nAccepted: {accepted:,}/{total:,}")

    if failures:
        print(f"\nFirst {min(5, len(failures))} failures:")
        for uid, reason in failures[:5]:
            print(f"  uid={uid} -> {reason}")


if __name__ == "__main__":
    main()
