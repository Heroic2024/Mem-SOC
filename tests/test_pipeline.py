"""
Contract tests for the MemSOC log-generation pipeline.

These guard the things that silently break the experiment rather than
throwing: the 48-feature contract drifting out of sync with the model's
drop list, ground truth leaking into the log stream, uid collisions, and
the seeded order stopping being reproducible.

Stdlib unittest only -- no new dependencies. Three tiers, each skipping
cleanly when its input is absent, so the suite is runnable on a fresh
clone and complete on a fully set-up machine:

    schema     always runs (parses feature_engineering.py)
    artifact   needs generated_logs.jsonl  (run_pipeline.py --regenerate)
    live       needs the API healthy       (run_pipeline.py leaves it up,
                                            or start it with --no-api off)

Usage:
    python -m unittest test_pipeline -v
    python -m unittest discover -s tests -v
"""

import ast
import csv
import json
import os
import sys
import unittest

import pandas as pd
import requests

from memsoc import paths
from memsoc.logstream import nfv3_log_generator as generator

FEATURE_ENGINEERING = paths.FEATURE_ENGINEERING

API_BASE = paths.API_BASE
API_HEALTH = paths.API_HEALTH
API_URL = paths.API_URL

ENVELOPE_KEYS = {
    "uid", "ts", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p", "proto",
}

LIVE_SAMPLE = 30   # records POSTed in the live tier (seeded order: first attack at 17)


# ---------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------
def load_logs(limit=None):
    if not os.path.exists(generator.OUTPUT_JSONL):
        return None

    records = []
    with open(generator.OUTPUT_JSONL, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            records.append(json.loads(line))
            if limit is not None and len(records) >= limit:
                break
    return records


def api_is_up():
    try:
        return requests.get(API_HEALTH, timeout=2).status_code == 200
    except requests.RequestException:
        return False


def drop_list_from_source():
    """
    Read the drop list out of feature_engineering.py rather than trusting
    a copy of it. If the model's preprocessing changes, this is what
    catches the generator drifting away from it.
    """

    with open(FEATURE_ENGINEERING, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    best = None

    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)):
            continue

        values = [
            e.value for e in node.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]

        if len(values) != len(node.elts):
            continue

        # The drop list is the one containing both target columns.
        if {"Label", "Attack"} <= set(values):
            if best is None or len(values) > len(best):
                best = values

    return best


# ---------------------------------------------------------------------
# TIER 1: schema contract
# ---------------------------------------------------------------------
class TestSchemaContract(unittest.TestCase):

    def test_drop_list_matches_the_model_source(self):
        """The generator's DROP_COLUMNS must equal the model's own list."""

        source_list = drop_list_from_source()

        self.assertIsNotNone(
            source_list,
            f"no drop list found in {FEATURE_ENGINEERING}",
        )
        self.assertEqual(
            sorted(source_list),
            sorted(generator.DROP_COLUMNS),
            "DROP_COLUMNS has drifted from feature_engineering.py",
        )

    def test_seven_columns_are_dropped(self):
        """2 targets + 5 metadata. DNS_QUERY_ID is the easily-missed one."""

        self.assertEqual(len(generator.DROP_COLUMNS), 7)
        self.assertIn("DNS_QUERY_ID", generator.DROP_COLUMNS)

    def test_dataset_header_yields_48_features(self):
        if not os.path.exists(generator.INPUT_CSV):
            self.skipTest("NF-UNSW-NB15-v3.csv not present")

        columns = list(pd.read_csv(generator.INPUT_CSV, nrows=0).columns)

        self.assertEqual(len(columns), 55, "dataset is no longer 55 columns")
        self.assertEqual(len(generator.read_feature_columns(generator.INPUT_CSV)), 48)


# ---------------------------------------------------------------------
# TIER 2: generated artifact
# ---------------------------------------------------------------------
class TestGeneratedLogs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = load_logs()
        if cls.records is None:
            raise unittest.SkipTest(
                f"{generator.OUTPUT_JSONL} not present -- "
                "run: python run_pipeline.py --regenerate"
            )

        cls.features = (
            generator.read_feature_columns(generator.INPUT_CSV)
            if os.path.exists(generator.INPUT_CSV)
            else sorted(set(cls.records[0]) - ENVELOPE_KEYS)
        )

    def test_every_record_carries_all_48_features(self):
        for i, record in enumerate(self.records, start=1):
            missing = [c for c in self.features if c not in record]
            self.assertFalse(missing, f"record {i} missing: {missing}")

    def test_features_are_flat_at_top_level(self):
        """validate_input() looks at top-level keys; nesting fails silently."""

        record = self.records[0]

        for column in self.features:
            self.assertNotIsInstance(
                record[column], (dict, list),
                f"{column} is nested; the pipeline will not find it",
            )

    def test_no_ground_truth_leaks_into_the_log(self):
        """Label/Attack are the evaluation oracle and must never be emitted."""

        for i, record in enumerate(self.records, start=1):
            for forbidden in ("Label", "Attack", "label", "attack"):
                self.assertNotIn(
                    forbidden, record,
                    f"record {i} leaks ground truth via '{forbidden}'",
                )

    def test_all_feature_values_are_finite_numbers(self):
        """Mirrors prepare_dataframe(): a NaN here is an HTTP 400 later."""

        for i, record in enumerate(self.records, start=1):
            bad = [
                c for c in self.features
                if pd.isna(pd.to_numeric(record[c], errors="coerce"))
            ]
            self.assertFalse(bad, f"record {i} non-numeric in: {bad}")

    def test_uids_are_unique(self):
        uids = [r["uid"] for r in self.records]

        self.assertEqual(
            len(uids), len(set(uids)),
            "uid collision -- ground truth can no longer be joined",
        )

    def test_ground_truth_sidecar_joins_one_to_one(self):
        if not os.path.exists(generator.GROUND_TRUTH_CSV):
            self.skipTest(f"{generator.GROUND_TRUTH_CSV} not present")

        with open(generator.GROUND_TRUTH_CSV, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), len(self.records))
        self.assertEqual(
            {r["uid"] for r in rows},
            {r["uid"] for r in self.records},
            "ground truth uids do not match the log uids",
        )
        for row in rows:
            self.assertIn(row["label"], ("0", "1"))


# ---------------------------------------------------------------------
# TIER 3: live API acceptance
# ---------------------------------------------------------------------
class TestLiveInference(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not api_is_up():
            raise unittest.SkipTest(
                f"no healthy API at {API_BASE} -- "
                "run: python run_pipeline.py"
            )

        cls.records = load_logs(LIVE_SAMPLE)
        if not cls.records:
            raise unittest.SkipTest(f"{generator.OUTPUT_JSONL} not present")

    def test_every_record_is_accepted(self):
        for record in self.records:
            response = requests.post(API_URL, json=record, timeout=30)

            self.assertEqual(
                response.status_code, 200,
                f"uid={record['uid']} rejected: {response.text[:200]}",
            )

    def test_response_carries_a_binary_verdict(self):
        result = requests.post(API_URL, json=self.records[0], timeout=30).json()

        self.assertIn("status", result)
        self.assertIn("binary", result)
        self.assertIn("prediction", result["binary"])
        self.assertIsInstance(result["binary"]["confidence"], (int, float))

    def test_attack_responses_carry_multiclass_shap_and_alert(self):
        """The enrichment path only fires on attacks; skip if none in sample."""

        for record in self.records:
            result = requests.post(API_URL, json=record, timeout=30).json()

            if result.get("status") != "attack":
                continue

            self.assertTrue(result.get("multiclass"), "attack without category")
            self.assertTrue(result.get("shap"), "attack without SHAP")
            self.assertTrue(result.get("alert"), "attack without alert")
            return

        self.skipTest(f"no attack flows in the first {LIVE_SAMPLE} records")

    def test_a_record_missing_a_feature_is_rejected(self):
        """Negative control: the contract is actually enforced, not assumed."""

        record = dict(self.records[0])
        feature = next(k for k in record if k not in ENVELOPE_KEYS)
        del record[feature]

        response = requests.post(API_URL, json=record, timeout=30)

        self.assertEqual(
            response.status_code, 400,
            f"dropping {feature} should have been rejected",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
