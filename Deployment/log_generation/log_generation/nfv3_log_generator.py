"""
NF-UNSW-NB15-v3 -> 48-feature JSONL logs for the MemSOC inference API.

Produces logs that POST /api/logs (final_ml_model_v1) accepts as-is:
every record carries the exact 48 model features flat at top level, plus
a small Zeek-style envelope (uid/ts/addresses/proto) that the pipeline
ignores but that makes the stream look like real sensor output.

Pipeline:
      NF-UNSW-NB15-v3.csv  (55 columns, 2.36M rows)
                |
                v   drop non-finite -> seeded selection -> seeded shuffle
      generated_logs.jsonl   (envelope + 48 features)
      ground_truth.csv       (uid,label,attack -- held out)

Ground truth is written to a SEPARATE file, never into the log. See README.

Note on non-finite rows: ~5.18% of the dataset carries NaN or inf in
SRC_TO_DST_SECOND_BYTES / DST_TO_SRC_SECOND_BYTES. The inference pipeline
rejects those with HTTP 400, so they are excluded here and the excluded
count is reported. See README for the caveat this implies.

Usage:
    python nfv3_log_generator.py
"""

import json
import os
import sys

import numpy as np
import pandas as pd

# Repo root on sys.path: every path in this project comes from paths.py,
# so the script behaves the same from any working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------
INPUT_CSV = paths.DATASET_CSV
OUTPUT_JSONL = paths.GENERATED_LOGS
GROUND_TRUTH_CSV = paths.GROUND_TRUTH

SEED = 42

# The controller can override this value using MEMSOC_SAMPLE_SIZE.
# If no value is provided, the default remains 5000.
SAMPLE_SIZE = int(os.environ.get("MEMSOC_SAMPLE_SIZE", "5000"))

CHUNK_SIZE = 200_000

PROTO_MAP = {6: "tcp", 17: "udp", 1: "icmp"}

# Not model inputs. Mirrors final_ml_model_v1/src/features/feature_engineering.py
# and final_ml_model_v1/test_api.py -- 2 targets + 5 metadata columns.
DROP_COLUMNS = [
    "Attack",
    "Label",
    "IPV4_SRC_ADDR",
    "IPV4_DST_ADDR",
    "FLOW_START_MILLISECONDS",
    "FLOW_END_MILLISECONDS",
    "DNS_QUERY_ID",
]

EXPECTED_FEATURE_COUNT = 48


# ---------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------
def read_feature_columns(path: str) -> list:

    header = pd.read_csv(path, nrows=0)

    columns = [c.strip() for c in header.columns]

    features = [c for c in columns if c not in DROP_COLUMNS]

    if len(features) != EXPECTED_FEATURE_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_FEATURE_COUNT} model features, "
            f"got {len(features)}. Dataset schema has changed."
        )

    return features


def eligible_mask(chunk: pd.DataFrame, feature_columns: list) -> pd.Series:
    """
    Rows every feature of which is finite and numeric.

    Mirrors the check prepare_dataframe() applies in the inference
    pipeline, so anything that would come back as HTTP 400 is filtered
    here rather than failing mid-replay.
    """

    numeric = chunk[feature_columns].apply(
        pd.to_numeric,
        errors="coerce"
    )

    return ~(numeric.isna() | np.isinf(numeric.fillna(0))).any(axis=1)


# ---------------------------------------------------------------------
# STEP 1: Seeded selection over eligible rows
# ---------------------------------------------------------------------
def count_eligible(path: str, feature_columns: list) -> tuple:

    total = 0
    eligible = 0

    for chunk_num, chunk in enumerate(
        pd.read_csv(path, chunksize=CHUNK_SIZE), start=1
    ):
        chunk.columns = [c.strip() for c in chunk.columns]

        total += len(chunk)
        eligible += int(eligible_mask(chunk, feature_columns).sum())

        print(
            f"[scan {chunk_num}] "
            f"{total:,} rows -- {eligible:,} eligible"
        )

    return total, eligible


def select_rows(path: str, feature_columns: list, eligible_total: int):

    if SAMPLE_SIZE > eligible_total:
        raise ValueError(
            f"SAMPLE_SIZE ({SAMPLE_SIZE}) exceeds eligible rows "
            f"({eligible_total})"
        )

    rng = np.random.default_rng(SEED)

    wanted = set(
        rng.choice(
            eligible_total,
            size=SAMPLE_SIZE,
            replace=False
        ).tolist()
    )

    kept = []
    offset = 0
    found = 0

    for chunk_num, chunk in enumerate(
        pd.read_csv(path, chunksize=CHUNK_SIZE), start=1
    ):
        chunk.columns = [c.strip() for c in chunk.columns]

        chunk = chunk[eligible_mask(chunk, feature_columns)]

        positions = [
            i for i in range(len(chunk))
            if offset + i in wanted
        ]

        if positions:
            kept.append(chunk.iloc[positions])
            found += len(positions)

        offset += len(chunk)

        print(
            f"[select {chunk_num}] "
            f"{offset:,}/{eligible_total:,} eligible scanned "
            f"-- {found:,}/{SAMPLE_SIZE:,} selected"
        )

        if found == SAMPLE_SIZE:
            break

    df = pd.concat(kept, ignore_index=True)

    # Seeded shuffle: the stream order looks unpredictable to the model,
    # but replays identically on every run.
    return df.sample(
        frac=1,
        random_state=SEED
    ).reset_index(drop=True)


# ---------------------------------------------------------------------
# STEP 2: Row -> JSON record
# ---------------------------------------------------------------------
def to_native(value):
    """pandas yields numpy scalars, which json.dumps cannot serialize."""

    if isinstance(value, np.generic):
        return value.item()

    return value


def build_record(row: pd.Series, seq: int, feature_columns: list) -> dict:

    flow_start = int(row["FLOW_START_MILLISECONDS"])
    src_port = int(row["L4_SRC_PORT"])
    proto_num = int(row["PROTOCOL"])

    # Separated + sequence-suffixed so uids cannot collide.
    record = {
        "uid": f"C{flow_start}-{src_port}-{seq}",
        "ts": round(flow_start / 1000, 6),
        "id.orig_h": str(row["IPV4_SRC_ADDR"]),
        "id.orig_p": src_port,
        "id.resp_h": str(row["IPV4_DST_ADDR"]),
        "id.resp_p": int(row["L4_DST_PORT"]),
        "proto": PROTO_MAP.get(proto_num, str(proto_num)),
    }

    # The 48 model features, flat at top level under their exact
    # dataset column names -- this is what validate_input() looks for.
    for column in feature_columns:
        record[column] = to_native(row[column])

    return record


def validate_record(
    record: dict,
    feature_columns: list,
    seq: int
) -> None:

    missing = [
        c for c in feature_columns
        if c not in record
    ]

    if missing:
        raise ValueError(
            f"record {seq}: missing features: "
            f"{', '.join(missing)}"
        )

    # Same condition prepare_dataframe() raises on in the inference pipeline.
    bad = [
        c
        for c in feature_columns
        if pd.isna(
            pd.to_numeric(
                record[c],
                errors="coerce"
            )
        )
    ]

    if bad:
        raise ValueError(
            f"record {seq}: non-numeric feature values in: "
            f"{', '.join(bad)}"
        )


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def main():

    print("\n========== NF-UNSW-NB15 LOG GENERATION ==========\n")
    print(f"Source : {INPUT_CSV}")
    print(f"Seed   : {SEED}")
    print(f"Sample : {SAMPLE_SIZE:,} flows\n")

    feature_columns = read_feature_columns(INPUT_CSV)

    print(f"Model features: {len(feature_columns)}")

    print(
        f"Dropped       : {len(DROP_COLUMNS)} "
        f"(2 targets + {len(DROP_COLUMNS) - 2} metadata)\n"
    )

    total_rows, eligible_total = count_eligible(
        INPUT_CSV,
        feature_columns
    )

    excluded = total_rows - eligible_total

    print(f"\nDataset rows : {total_rows:,}")

    print(
        f"Excluded     : {excluded:,} "
        f"({excluded / total_rows:.2%}) "
        f"-- non-finite feature values"
    )

    print(f"Eligible     : {eligible_total:,}\n")

    df = select_rows(
        INPUT_CSV,
        feature_columns,
        eligible_total
    )

    benign = 0
    attack = 0

    # "w" means every new run replaces the previous logs
    # and previous ground-truth file.
    with open(
        OUTPUT_JSONL,
        "w",
        encoding="utf-8"
    ) as log_f, open(
        GROUND_TRUTH_CSV,
        "w",
        encoding="utf-8",
        newline=""
    ) as gt_f:

        gt_f.write("uid,label,attack\n")

        for seq, (_, row) in enumerate(
            df.iterrows(),
            start=1
        ):

            record = build_record(
                row,
                seq,
                feature_columns
            )

            validate_record(
                record,
                feature_columns,
                seq
            )

            log_f.write(
                json.dumps(record) + "\n"
            )

            label = int(row["Label"])

            gt_f.write(
                f"{record['uid']},{label},{row['Attack']}\n"
            )

            if label == 1:
                attack += 1
            else:
                benign += 1

    print(
        f"\nDone. {benign + attack:,} records "
        f"-> {OUTPUT_JSONL}"
    )

    print(
        f"Ground truth      -> {GROUND_TRUTH_CSV}"
    )

    print(
        f"Benign / Attack   : {benign:,} / {attack:,}"
    )


if __name__ == "__main__":
    main()