"""
Recover the rows the frozen detector never trained on, and prove it.

    python -m memsoc.detection.training.heldout_split

The detector's train/test split was never persisted: `split_data.py` returns
its arrays and the trainers dump only the model pickles. That is why the
replayed alert stream overlaps the training set (BL-025) and why every
detector figure measured on it is inflated (BL-028).

This module re-derives the split and then *verifies* the derivation against
the fingerprint the training run published in
`docs/detection/model-overview.md`. It fits nothing, retunes nothing and
writes no model. The frozen pickles are opened read-only, for scoring.

Two things make the verification possible:

  1. The row population is self-checking. 2,365,424 rows minus 14,815
     duplicates is 2,350,609, which is exactly 1,880,487 + 470,122; and
     102,143 + 25,536 is exactly the 127,679 attack rows. A derivation that
     hits all four numbers has the right population.

  2. The partition is checkable. The published fingerprint carries nine
     class-wise F1 values and an order-sensitive 72-of-100 on the first
     hundred test rows. Scoring the frozen multiclass pickle on a re-derived
     test set either reproduces that or it does not.

If the fingerprint does not reproduce, this script writes no index file and
exits non-zero. The manifest is written either way, because the observed
numbers are the evidence for whatever is decided next.

One subtlety the index alone does not cover. `drop_duplicates()` dedupes all
55 columns, so two rows that differ only in an address or a timestamp can
carry an identical 48-feature vector -- one of them trained on, the other
not. A row whose features the detector has already seen is not held out in
any useful sense, so rows whose feature-vector hash appears anywhere in
either training set are excluded as well. That clause is also what makes the
output safe if the partition recovery is only approximately right.
"""

import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

from memsoc import paths
from memsoc.detection.dataset.loader import DatasetLoader
from memsoc.detection.features.feature_engineering import FeatureEngineering
from memsoc.detection.preprocessing.preprocessor import DataPreprocessor
from memsoc.detection.utils.logger import logger


# ============================================================
# PUBLISHED FIGURES -- THE THING WE ARE CHECKING AGAINST
# ============================================================
# Every number below is transcribed from
# docs/detection/model-overview.md. They are the training run's own
# published output. Do not adjust them to make a derivation pass -- that
# would defeat the entire purpose of this script.

EXPECTED_ROWS_AFTER_DEDUP = 2_350_609

EXPECTED_BINARY_TRAIN = 1_880_487
EXPECTED_BINARY_TEST = 470_122

EXPECTED_ATTACK_TOTAL = 127_679
EXPECTED_ATTACK_TRAIN = 102_143
EXPECTED_ATTACK_TEST = 25_536

EXPECTED_ACCURACY_PCT = 75.62

# The two aggregate figures below are reported but are NOT part of the gate,
# because the document contradicts itself on them and they carry no
# information independent of the nine per-class values.
#
# Measured 2026-10-10: the mean of the nine published per-class F1 values is
# 62.9133, not the 63.02 published alongside them. Macro F1 is by definition
# that mean over the same label set, and the frozen pickle reports exactly
# nine classes (`classes_`), so a tenth class cannot account for the gap.
# A derivation that reproduces all nine per-class values therefore cannot
# reproduce 63.02 -- failing it on that would be testing the documentation's
# arithmetic, not the split. Weighted F1 is the same quantity weighted by
# support, and support is already pinned by the exact 25,536 test count.
#
# Tracked as BL-103. Do not promote these back into the gate without first
# resolving where 63.02 and 75.47 came from.
EXPECTED_WEIGHTED_F1_PCT = 75.47
EXPECTED_MACRO_F1_PCT = 63.02

EXPECTED_CLASS_F1_PCT = {
    "Generic": 89.82,
    "Fuzzers": 78.73,
    "Exploits": 76.89,
    "Reconnaissance": 73.49,
    "Shellcode": 68.11,
    "Worms": 58.06,
    "DoS": 45.85,
    "Analysis": 41.87,
    "Backdoor": 33.40,
}

EXPECTED_SAMPLE_CORRECT = 72
SAMPLE_TEST_SIZE = 100

# The published figures are given to two decimal places as percentages, so
# a reproduction can differ only by rounding.
TOLERANCE_PCT = 0.01


# ============================================================
# SPLIT PARAMETERS -- MUST MATCH split_data.py EXACTLY
# ============================================================
# Mirrored from split_data.py:20-26 and :49-55. If those ever change, the
# detector has been retrained and this module is invalid.

TEST_SIZE = 0.2
RANDOM_STATE = 42


def sha256_of(file_path):
    """Content hash of a file, so a model swap cannot go unnoticed."""

    digest = hashlib.sha256()

    with open(file_path, "rb") as handle:

        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


# ============================================================
# STAGE 1 -- REPLAY THE TRAINING PIPELINE'S ROW HANDLING
# ============================================================

def load_and_prepare():
    """
    Reproduce the exact frame the split was taken from.

    The order is the one run_training.py uses: load, remove duplicates,
    fill missing values, then build the feature matrix. `read_csv` gives a
    RangeIndex and neither `drop_duplicates` nor `drop(columns=...)`
    disturbs index labels, so every label here is the row's 0-based
    position in the CSV's data rows. That is the row identity the rest of
    this module relies on.
    """

    logger.info("========== HELD-OUT SPLIT RECOVERY ==========")

    # paths.py hands back strings; DatasetLoader expects a Path.
    loader = DatasetLoader(Path(paths.DATASET_CSV))

    df = loader.load()

    rows_before = len(df)

    df = DataPreprocessor(df).run()

    X, y_binary, y_multi = FeatureEngineering(df).run()

    logger.info(f"Rows as read        : {rows_before}")
    logger.info(f"Rows after dedup    : {len(df)}")
    logger.info(f"Feature columns     : {X.shape[1]}")

    if len(df) != EXPECTED_ROWS_AFTER_DEDUP:
        raise SystemExit(
            f"Row count after deduplication is {len(df)}, expected "
            f"{EXPECTED_ROWS_AFTER_DEDUP}. The dataset or the "
            f"preprocessing has changed; the recovered split would not be "
            f"the one the detector was trained on."
        )

    return X, y_binary, y_multi


# ============================================================
# STAGE 2 -- RE-DERIVE BOTH SPLITS
# ============================================================

def derive_splits(X, y_binary, y_multi):
    """
    Re-derive the two independent splits, carrying index labels only.

    `train_test_split`'s stratified shuffle depends on the sample count,
    the stratify vector and the random state -- not on what is being
    split. Passing the index array therefore produces the same partition
    as passing the 48-column matrix, without a second copy of it in
    memory.

    The two splits are independent, exactly as in split_data.py: the
    multiclass one is taken over attack rows only and is *not* a subset of
    the binary one. A row is only genuinely unseen if it sits outside both
    training sets.
    """

    logger.info("Re-deriving the binary split...")

    binary_index = X.index.to_numpy()

    binary_train_idx, binary_test_idx = train_test_split(
        binary_index,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y_binary.to_numpy()
    )

    logger.info(f"Binary train        : {len(binary_train_idx)}")
    logger.info(f"Binary test         : {len(binary_test_idx)}")

    check_count(
        "binary train", len(binary_train_idx), EXPECTED_BINARY_TRAIN
    )
    check_count(
        "binary test", len(binary_test_idx), EXPECTED_BINARY_TEST
    )

    # split_data.py:40-47 filters to attack rows before splitting, which
    # preserves the frame's order. The label vector drives the stratified
    # shuffle, so the filtered index is all that has to be carried.
    logger.info("Re-deriving the multiclass split...")

    attack_mask = (y_binary == 1).to_numpy()

    attack_index = X.index.to_numpy()[attack_mask]
    y_attack = y_multi.to_numpy()[attack_mask]

    check_count(
        "attack rows", len(attack_index), EXPECTED_ATTACK_TOTAL
    )

    attack_train_idx, attack_test_idx = train_test_split(
        attack_index,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y_attack
    )

    logger.info(f"Attack train        : {len(attack_train_idx)}")
    logger.info(f"Attack test         : {len(attack_test_idx)}")

    check_count(
        "attack train", len(attack_train_idx), EXPECTED_ATTACK_TRAIN
    )
    check_count(
        "attack test", len(attack_test_idx), EXPECTED_ATTACK_TEST
    )

    return (
        binary_train_idx,
        binary_test_idx,
        attack_train_idx,
        attack_test_idx,
    )


def check_count(label, observed, expected):
    """A size mismatch means the population is wrong. Stop immediately."""

    if observed != expected:
        raise SystemExit(
            f"{label} size is {observed}, expected {expected}. The "
            f"recovered split is not the detector's; nothing downstream "
            f"would be valid."
        )


# ============================================================
# STAGE 3 -- THE GATE
# ============================================================

def verify_fingerprint(X, y_multi, attack_test_idx):
    """
    Score the frozen multiclass pickle on the recovered test set and
    compare every published figure against it.

    The nine class-wise F1 values confirm set *membership*. The 72-of-100
    on the first hundred rows confirms the *order* as well, because
    run_training.py:168-181 walks `X_test_multi.iloc[0:100]` in the order
    train_test_split returned.

    Returns (passed, observed) and never raises on a mismatch -- the caller
    records the observed numbers either way.
    """

    logger.info("========== VERIFYING AGAINST PUBLISHED FIGURES ==========")

    model = joblib.load(paths.MULTICLASS_MODEL)

    X_test_multi = X.loc[attack_test_idx]
    y_test_multi = y_multi.loc[attack_test_idx]

    predictions = model.predict(X_test_multi)

    labels = sorted(EXPECTED_CLASS_F1_PCT)

    per_class = f1_score(
        y_test_multi,
        predictions,
        labels=labels,
        average=None,
        zero_division=0
    )

    observed = {
        "accuracy_pct": round(
            accuracy_score(y_test_multi, predictions) * 100, 4
        ),
        "weighted_f1_pct": round(
            f1_score(
                y_test_multi, predictions,
                average="weighted", zero_division=0
            ) * 100, 4
        ),
        "macro_f1_pct": round(
            f1_score(
                y_test_multi, predictions,
                average="macro", zero_division=0
            ) * 100, 4
        ),
        "class_f1_pct": {
            name: round(value * 100, 4)
            for name, value in zip(labels, per_class)
        },
    }

    # The order-sensitive check. Predicting the slice in one call is
    # equivalent to the loop's row-by-row predict and far faster.
    sample_size = min(SAMPLE_TEST_SIZE, len(X_test_multi))

    sample_predictions = model.predict(X_test_multi.iloc[0:sample_size])

    observed["sample_size"] = sample_size
    observed["sample_correct"] = int(
        (sample_predictions == y_test_multi.iloc[0:sample_size].to_numpy()).sum()
    )

    # ----------------------------------------------------
    # Report every comparison, pass or fail
    # ----------------------------------------------------

    gated = [("accuracy", observed["accuracy_pct"], EXPECTED_ACCURACY_PCT)]

    for name in labels:
        gated.append(
            (
                f"F1 {name}",
                observed["class_f1_pct"][name],
                EXPECTED_CLASS_F1_PCT[name],
            )
        )

    informational = [
        ("weighted F1", observed["weighted_f1_pct"], EXPECTED_WEIGHTED_F1_PCT),
        ("macro F1", observed["macro_f1_pct"], EXPECTED_MACRO_F1_PCT),
    ]

    failures = []

    logger.info(f"{'figure':<22}{'observed':>12}{'published':>12}   verdict")

    for name, got, want in gated:

        matched = abs(round(got, 2) - want) <= TOLERANCE_PCT

        logger.info(
            f"{name:<22}{got:>11.2f}%{want:>11.2f}%   "
            f"{'match' if matched else 'MISMATCH'}"
        )

        if not matched:
            failures.append(name)

    # Order-sensitive, and the strongest single piece of evidence: it depends
    # on the order train_test_split returned, not just set membership.
    sample_matched = (
        observed["sample_correct"] == EXPECTED_SAMPLE_CORRECT
        and sample_size == SAMPLE_TEST_SIZE
    )

    logger.info(
        f"{'first-100 correct':<22}"
        f"{observed['sample_correct']:>12}"
        f"{EXPECTED_SAMPLE_CORRECT:>12}   "
        f"{'match' if sample_matched else 'MISMATCH'}"
    )

    if not sample_matched:
        failures.append("first-100 correct")

    # Reported, never gated. See the note on EXPECTED_MACRO_F1_PCT.
    discrepancies = []

    for name, got, want in informational:

        matched = abs(round(got, 2) - want) <= TOLERANCE_PCT

        logger.info(
            f"{name + ' (ungated)':<22}{got:>11.2f}%{want:>11.2f}%   "
            f"{'match' if matched else 'differs -- see BL-103'}"
        )

        if not matched:
            discrepancies.append(name)

    observed["mismatches"] = failures
    observed["ungated_discrepancies"] = discrepancies

    if failures:
        logger.error(
            f"{len(failures)} gated figure(s) did not reproduce: "
            f"{', '.join(failures)}"
        )
    else:
        logger.info(
            "Every gated figure reproduced, including the order-sensitive "
            "first-100 check. The recovered split is the detector's own."
        )

    if discrepancies:
        logger.warning(
            f"Ungated figures differ from the document: "
            f"{', '.join(discrepancies)}. These are derived from the "
            f"per-class values above, which all matched, so the document is "
            f"internally inconsistent rather than the split being wrong "
            f"(BL-103)."
        )

    return (not failures), observed


# ============================================================
# STAGE 4 -- BUILD THE HELD-OUT SET
# ============================================================

def build_held_out(
    X, y_binary, y_multi, binary_train_idx, binary_test_idx,
    attack_train_idx, attack_test_idx
):
    """
    Rows outside both training sets, minus any whose features were seen.

    A benign row is held out if it is in the binary test set. An attack row
    is held out only if it is in the binary test set *and* the multiclass
    test set, because the two splits are independent -- this is where the
    pool turns out to be far smaller than the binary test set alone
    (BL-100).

    The feature-hash subtraction then removes rows the detector has
    effectively already seen: `drop_duplicates()` compared all 55 columns,
    so a row can be unique overall while its 48 features are not.
    """

    logger.info("========== BUILDING THE HELD-OUT SET ==========")

    binary_test = set(binary_test_idx.tolist())
    attack_test = set(attack_test_idx.tolist())

    is_attack = (y_binary == 1)

    benign_index = set(X.index[~is_attack].tolist())
    attack_index = set(X.index[is_attack].tolist())

    held_out_benign = binary_test & benign_index
    held_out_attack = (binary_test & attack_index) & attack_test

    candidates = held_out_benign | held_out_attack

    logger.info(f"Held-out benign     : {len(held_out_benign)}")
    logger.info(f"Held-out attack     : {len(held_out_attack)}")
    logger.info(f"Candidate rows      : {len(candidates)}")

    # ----------------------------------------------------
    # Feature-vector exclusion
    # ----------------------------------------------------

    logger.info("Hashing feature vectors to exclude seen rows...")

    row_hash = pd.util.hash_pandas_object(X, index=False)

    trained_on = set(binary_train_idx.tolist()) | set(
        attack_train_idx.tolist()
    )

    seen_hashes = set(
        row_hash.loc[sorted(trained_on)].to_numpy().tolist()
    )

    candidate_list = sorted(candidates)

    candidate_hashes = row_hash.loc[candidate_list].to_numpy()

    keep_mask = np.array(
        [h not in seen_hashes for h in candidate_hashes.tolist()],
        dtype=bool
    )

    held_out = np.array(candidate_list, dtype=np.int64)[keep_mask]

    excluded = len(candidate_list) - len(held_out)

    logger.info(f"Excluded by features: {excluded}")
    logger.info(f"Held-out rows final : {len(held_out)}")

    # How many of the survivors are attacks -- the number that actually
    # decides whether a rebuilt stream can carry enough alerts.
    held_out_set = set(held_out.tolist())

    attack_surviving = len(held_out_set & attack_index)

    logger.info(f"  of which attacks  : {attack_surviving}")

    if len(held_out):
        logger.info(
            f"  attack base rate  : "
            f"{attack_surviving / len(held_out) * 100:.2f}%"
        )

    # ----------------------------------------------------
    # Per-class composition of the clean attack pool
    # ----------------------------------------------------
    # This is the number that decides whether a rebuilt stream can carry
    # a usable sample, and whether the rare classes survive at all
    # (BL-100). A class with single-digit support cannot be reported per
    # class no matter how the stream is sampled.

    held_out_attack_index = sorted(held_out_set & attack_index)

    class_counts = (
        y_multi.loc[held_out_attack_index]
        .value_counts()
        .sort_values(ascending=False)
    )

    logger.info("Clean attack pool by class:")

    for name, count in class_counts.items():
        logger.info(f"  {name:<18}{count:>8}")

    return held_out, {
        "held_out_benign": len(held_out_benign),
        "held_out_attack_before_feature_exclusion": len(held_out_attack),
        "candidates": len(candidate_list),
        "excluded_by_feature_hash": excluded,
        "held_out_total": int(len(held_out)),
        "held_out_attacks": attack_surviving,
        "held_out_attack_base_rate_pct": (
            round(attack_surviving / len(held_out) * 100, 4)
            if len(held_out) else 0.0
        ),
        "held_out_attacks_by_class": {
            str(name): int(count) for name, count in class_counts.items()
        },
    }


# ============================================================
# ENTRY POINT
# ============================================================

def main():

    X, y_binary, y_multi = load_and_prepare()

    (
        binary_train_idx,
        binary_test_idx,
        attack_train_idx,
        attack_test_idx,
    ) = derive_splits(X, y_binary, y_multi)

    passed, observed = verify_fingerprint(X, y_multi, attack_test_idx)

    held_out, counts = build_held_out(
        X, y_binary, y_multi, binary_train_idx, binary_test_idx,
        attack_train_idx, attack_test_idx
    )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_csv": paths.DATASET_CSV,
        "verification_passed": passed,
        "published": {
            "accuracy_pct": EXPECTED_ACCURACY_PCT,
            "weighted_f1_pct": EXPECTED_WEIGHTED_F1_PCT,
            "macro_f1_pct": EXPECTED_MACRO_F1_PCT,
            "class_f1_pct": EXPECTED_CLASS_F1_PCT,
            "sample_correct": EXPECTED_SAMPLE_CORRECT,
            "source": "docs/detection/model-overview.md",
            "gated": [
                "accuracy_pct",
                "class_f1_pct",
                "sample_correct",
            ],
            "ungated": {
                "figures": ["weighted_f1_pct", "macro_f1_pct"],
                "reason": (
                    "Derived from class_f1_pct, which matched in full. The "
                    "mean of the nine published per-class F1 values is "
                    "62.9133, not the 63.02 published beside them, and the "
                    "frozen pickle has exactly nine classes, so the "
                    "document is internally inconsistent. See BL-103."
                ),
            },
        },
        "observed": observed,
        "split": {
            "test_size": TEST_SIZE,
            "random_state": RANDOM_STATE,
            "binary_train": len(binary_train_idx),
            "binary_test": len(binary_test_idx),
            "attack_train": len(attack_train_idx),
            "attack_test": len(attack_test_idx),
        },
        "held_out": counts,
        "models": {
            "binary_sha256": sha256_of(paths.BINARY_MODEL),
            "multiclass_sha256": sha256_of(paths.MULTICLASS_MODEL),
        },
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scikit_learn": __import__("sklearn").__version__,
            "joblib": joblib.__version__,
        },
    }

    os.makedirs(os.path.dirname(paths.HELD_OUT_MANIFEST), exist_ok=True)

    with open(paths.HELD_OUT_MANIFEST, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")

    logger.info(f"Manifest written    : {paths.HELD_OUT_MANIFEST}")

    # The index file is the thing other layers consume, so it is written
    # only when the derivation is proven. The manifest above records the
    # observed figures regardless, because those are the evidence for
    # whatever gets decided next.
    if not passed:
        logger.error(
            "Fingerprint did not reproduce -- no index file written. The "
            "recovered partition is not demonstrably the detector's, so a "
            "stream built from it would not be demonstrably held out."
        )
        return 1

    np.save(paths.HELD_OUT_ROWS, held_out)

    logger.info(f"Index written       : {paths.HELD_OUT_ROWS}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
