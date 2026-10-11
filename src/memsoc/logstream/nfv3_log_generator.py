"""
NF-UNSW-NB15-v3 -> 48-feature JSONL logs for the MemSOC inference API.

Produces logs that POST /api/logs (final_ml_model_v1) accepts as-is:
every record carries the exact 48 model features flat at top level, plus
a small Zeek-style envelope (uid/ts/addresses/proto) that the pipeline
ignores but that makes the stream look like real sensor output.

Pipeline:
      NF-UNSW-NB15-v3.csv  (55 columns, 2.36M rows)
                |
                v   restrict to held-out rows -> drop non-finite
                v   -> seeded selection -> seeded shuffle
      generated_logs.jsonl   (envelope + 48 features)
      ground_truth.csv       (uid,label,attack -- held out)

Ground truth is written to a SEPARATE file, never into the log. See README.

Stream version 2 (2026-10-10): the pool is restricted to rows the frozen
detector never trained on. Version 1 sampled the whole dataset and so
overlapped the training set on 82% of its flows, which inflated every
detector figure measured against it (BL-025). The held-out row numbers come
from artifacts/heldout_rows.npy, produced and verified by
`memsoc.detection.training.heldout_split` -- run that first.

The restriction costs sample density, and the cost is the reason SAMPLE_SIZE
moved: the held-out pool is 1.13% attacks against 5.43% in the full dataset,
because the binary and multiclass splits are independent and an unseen attack
row has to sit outside both training sets (BL-100).

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

from memsoc import paths

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------
INPUT_CSV = paths.DATASET_CSV
OUTPUT_JSONL = paths.GENERATED_LOGS
GROUND_TRUTH_CSV = paths.GROUND_TRUTH
HELD_OUT_ROWS = paths.HELD_OUT_ROWS

SEED = 42              # fixed: same seed -> byte-identical output

# Bumped whenever the sampled POPULATION changes, which is not the same thing
# as changing the seed. Records carrying different stream versions are not
# comparable and must never be pooled.
STREAM_VERSION = "2"

# Flows to draw from the eligible pool. The controller overrides this per run
# via MEMSOC_SAMPLE_SIZE; the seed is NOT overridable, so a given sample size
# always yields the same sequence.
#
# 25,000 rather than 5,000 because the pool is now held-out only. At a 1.13%
# attack base rate, 5,000 flows would yield about 56 attacks -- fewer than the
# 211 the contaminated stream produced, and far short of the several hundred
# alerts the evaluation needs. 25,000 yields roughly 280.
SAMPLE_SIZE = int(os.environ.get("MEMSOC_SAMPLE_SIZE", "25000"))

CHUNK_SIZE = 200_000   # rows held in memory at once

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


def load_held_out() -> np.ndarray:
    """
    The raw CSV row numbers the frozen detector never trained on.

    Produced by `memsoc.detection.training.heldout_split`, which only
    writes this file once it has reproduced the detector's published
    fingerprint -- so its presence is itself the evidence that the
    restriction below is meaningful.
    """

    if not os.path.exists(HELD_OUT_ROWS):
        raise SystemExit(
            f"Held-out row index not found: {HELD_OUT_ROWS}\n"
            f"Run it first:\n"
            f"    python -m memsoc.detection.training.heldout_split\n"
            f"Without it this generator would sample the whole dataset and "
            f"the stream would overlap the detector's training set (BL-025)."
        )

    held_out = np.load(HELD_OUT_ROWS)

    print(f"Held-out rows loaded: {len(held_out):,}")

    return held_out


def pool_mask(
    chunk: pd.DataFrame, feature_columns: list, held_out: np.ndarray
) -> pd.Series:
    """
    The sampling pool: eligible AND never trained on.

    Both passes below MUST compose the pool through this one function. The
    selection pass tracks offsets *within the pool*, so if the counting
    pass and the selection pass defined the pool even slightly
    differently, the offsets would silently refer to different rows and
    the stream would be wrong without anything raising.

    `pd.read_csv(chunksize=...)` continues its RangeIndex across chunks,
    so `chunk.index` already holds raw 0-based CSV data-row numbers -- the
    same identity `heldout_split.py` wrote out, because `drop_duplicates()`
    preserves index labels.
    """

    return (
        eligible_mask(chunk, feature_columns)
        & chunk.index.isin(held_out)
    )


# ---------------------------------------------------------------------
# STEP 1: Seeded selection over the pool (never loads the whole file)
# ---------------------------------------------------------------------
def count_eligible(
    path: str, feature_columns: list, held_out: np.ndarray
) -> tuple:

    total = 0
    eligible = 0

    for chunk_num, chunk in enumerate(
        pd.read_csv(path, chunksize=CHUNK_SIZE), start=1
    ):
        chunk.columns = [c.strip() for c in chunk.columns]

        total += len(chunk)
        eligible += int(pool_mask(chunk, feature_columns, held_out).sum())

        print(f"[scan {chunk_num}] {total:,} rows -- {eligible:,} in pool")

    return total, eligible


def select_rows(
    path: str, feature_columns: list, eligible_total: int,
    held_out: np.ndarray
):

    if SAMPLE_SIZE > eligible_total:
        raise ValueError(
            f"SAMPLE_SIZE ({SAMPLE_SIZE}) exceeds eligible rows "
            f"({eligible_total})"
        )

    rng = np.random.default_rng(SEED)

    wanted = set(
        rng.choice(eligible_total, size=SAMPLE_SIZE, replace=False).tolist()
    )

    kept = []
    offset = 0   # position within the eligible pool, not the raw file
    found = 0

    for chunk_num, chunk in enumerate(
        pd.read_csv(path, chunksize=CHUNK_SIZE), start=1
    ):
        chunk.columns = [c.strip() for c in chunk.columns]

        chunk = chunk[pool_mask(chunk, feature_columns, held_out)]

        positions = [
            i for i in range(len(chunk)) if offset + i in wanted
        ]

        if positions:
            selected = chunk.iloc[positions]

            # Carried through the concat below, which otherwise discards the
            # index. This is what lets anyone check afterwards that every
            # streamed flow really came from the held-out pool.
            selected = selected.assign(row_id=selected.index)

            kept.append(selected)
            found += len(positions)

        offset += len(chunk)

        print(
            f"[select {chunk_num}] {offset:,}/{eligible_total:,} pool "
            f"scanned -- {found:,}/{SAMPLE_SIZE:,} selected"
        )

        if found == SAMPLE_SIZE:
            break

    df = pd.concat(kept, ignore_index=True)

    # Seeded shuffle: the stream order looks unpredictable to the model,
    # but replays identically on every run.
    return df.sample(frac=1, random_state=SEED).reset_index(drop=True)


# ---------------------------------------------------------------------
# STEP 2: Row -> JSON record
# ---------------------------------------------------------------------
def to_native(value):
    """pandas yields numpy scalars, which json.dumps cannot serialize."""

    if isinstance(value, np.generic):
        return value.item()

    return value


def build_record(
    row, seq: int, feature_columns: list, stream_version: str = None
) -> dict:
    """
    One row -> one API-shaped log record.

    `row` is a pandas Series from this module and a plain dict from
    stream_to_api.py, so only operations both support are used.

    The provenance keys are written only when the caller can honestly
    supply them. stream_to_api.py seeks rows through a byte-offset index
    that carries no row identity and applies no held-out restriction, so
    it passes neither -- and a record lacking these keys is therefore one
    whose population is *not* known to exclude the detector's training
    set. Defaulting them would turn that into a silent false claim.
    """

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

    if "row_id" in row:
        record["row_id"] = int(row["row_id"])

    if stream_version is not None:
        record["stream_version"] = stream_version

    # The 48 model features, flat at top level under their exact
    # dataset column names -- this is what validate_input() looks for.
    for column in feature_columns:
        record[column] = to_native(row[column])

    return record


def validate_record(record: dict, feature_columns: list, seq: int) -> None:

    missing = [c for c in feature_columns if c not in record]

    if missing:
        raise ValueError(
            f"record {seq}: missing features: {', '.join(missing)}"
        )

    # Same condition prepare_dataframe() raises on in the inference pipeline.
    bad = [
        c for c in feature_columns
        if pd.isna(pd.to_numeric(record[c], errors="coerce"))
    ]

    if bad:
        raise ValueError(
            f"record {seq}: non-numeric feature values in: {', '.join(bad)}"
        )


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def main():

    print("\n========== NF-UNSW-NB15 LOG GENERATION ==========\n")
    print(f"Source : {INPUT_CSV}")
    print(f"Seed   : {SEED}")
    print(f"Stream : version {STREAM_VERSION} (held-out rows only)")
    print(f"Sample : {SAMPLE_SIZE:,} flows\n")

    held_out = load_held_out()

    feature_columns = read_feature_columns(INPUT_CSV)

    print(f"Model features: {len(feature_columns)}")
    print(
        f"Dropped       : {len(DROP_COLUMNS)} "
        f"(2 targets + {len(DROP_COLUMNS) - 2} metadata)\n"
    )

    total_rows, eligible_total = count_eligible(
        INPUT_CSV, feature_columns, held_out
    )

    excluded = total_rows - eligible_total

    print(f"\nDataset rows : {total_rows:,}")
    print(
        f"Excluded     : {excluded:,} "
        f"({excluded / total_rows:.2%}) -- not held out, or non-finite"
    )
    print(f"Sampling pool: {eligible_total:,}\n")

    df = select_rows(
        INPUT_CSV, feature_columns, eligible_total, held_out
    )

    benign = 0
    attack = 0

    with open(OUTPUT_JSONL, "w", encoding="utf-8") as log_f, \
            open(GROUND_TRUTH_CSV, "w", encoding="utf-8", newline="") as gt_f:

        gt_f.write("uid,label,attack\n")

        for seq, (_, row) in enumerate(df.iterrows(), start=1):

            record = build_record(
                row, seq, feature_columns, STREAM_VERSION
            )

            validate_record(record, feature_columns, seq)

            log_f.write(json.dumps(record) + "\n")

            label = int(row["Label"])

            gt_f.write(f"{record['uid']},{label},{row['Attack']}\n")

            if label == 1:
                attack += 1
            else:
                benign += 1

    print(f"\nDone. {benign + attack:,} records -> {OUTPUT_JSONL}")
    print(f"Ground truth      -> {GROUND_TRUTH_CSV}")
    print(f"Benign / Attack   : {benign:,} / {attack:,}")


if __name__ == "__main__":
    main()
