"""
Convert an already-generated generated_conn.log (space-separated,
Zeek conn.log-style) directly into JSON Lines (JSONL) format --
no need to reprocess the original CSV.

Expects each line in this field order (as produced by
template_convert.py / template_convert_fast.py):

ts uid id.orig_h id.orig_p id.resp_h id.resp_p proto duration \
orig_bytes resp_bytes orig_pkts resp_pkts tcp_flags min_ttl max_ttl

Note: label/attack columns are intentionally excluded -- see README.

Usage:
    python3 log_to_jsonl.py
"""

import json

INPUT_LOG = "generated_conn.log"
OUTPUT_JSONL = "generated_logs.jsonl"

FIELD_ORDER = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
    "proto", "duration", "orig_bytes", "resp_bytes", "orig_pkts",
    "resp_pkts", "tcp_flags", "min_ttl", "max_ttl",
]

# fields that should be cast to int/float rather than left as strings
INT_FIELDS = {
    "id.orig_p", "id.resp_p", "orig_bytes", "resp_bytes",
    "orig_pkts", "resp_pkts", "tcp_flags", "min_ttl", "max_ttl",
}
FLOAT_FIELDS = {"ts", "duration"}


def parse_line(line: str) -> dict:
    parts = line.strip().split()
    if len(parts) != len(FIELD_ORDER):
        raise ValueError(
            f"expected {len(FIELD_ORDER)} fields, got {len(parts)}: {line!r}"
        )

    record = {}
    for field, value in zip(FIELD_ORDER, parts):
        if field in INT_FIELDS:
            record[field] = int(value)
        elif field in FLOAT_FIELDS:
            record[field] = float(value)
        else:
            record[field] = value
    return record


def main():
    total = 0
    errors = 0

    with open(INPUT_LOG, "r") as in_f, open(OUTPUT_JSONL, "w") as out_f:
        for line_num, line in enumerate(in_f, start=1):
            if not line.strip():
                continue
            try:
                record = parse_line(line)
                out_f.write(json.dumps(record) + "\n")
                total += 1
            except ValueError as e:
                errors += 1
                print(f"[SKIP] line {line_num}: {e}")

    print(f"\nDone. {total} lines converted -> {OUTPUT_JSONL}")
    if errors:
        print(f"{errors} lines skipped due to formatting issues")


if __name__ == "__main__":
    main()
