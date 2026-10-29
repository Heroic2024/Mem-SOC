"""
Tests for the statistical/cost additions to score_verdicts.py (Wilson
intervals, exact McNemar, the confusion matrix, the B1 escalation
metric, and four further extensions -- see that module's own comment
block for why each exists).

Offline, stdlib-only fixtures. No real run data, no API key, no
network -- per the plan, these are checked against hand-built fixtures
with known answers first. The one cross-check against a real, already-
published number (Qwen's McNemar p = 0.0625) is included explicitly,
since it's a case where the exact answer is independently known.

    python -m unittest tests.test_score_verdicts -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memsoc.triage import score_verdicts as sv


def gt_row(uid, attack):
    return {"uid": uid, "attack": attack}


def verdict_row(uid, verdict, category, detector_label="X", dst_port=80,
                 protocol=6, seq=0, latency_ms=100, **extra):
    row = {
        "uid": uid, "verdict": verdict, "attack_category": category,
        "detector_label": detector_label, "dst_port": dst_port,
        "protocol": protocol, "seq": seq, "latency_ms": latency_ms,
    }
    row.update(extra)
    return row


class WilsonIntervalTests(unittest.TestCase):

    def test_zero_n_returns_zero_interval(self):
        self.assertEqual(sv.wilson_interval(0, 0), (0.0, 0.0))

    def test_bounds_are_within_0_and_1(self):
        lo, hi = sv.wilson_interval(5, 10)
        self.assertGreaterEqual(lo, 0.0)
        self.assertLessEqual(hi, 1.0)
        self.assertLess(lo, hi)

    def test_interval_contains_the_point_estimate(self):
        lo, hi = sv.wilson_interval(66, 164)
        phat = 66 / 164
        self.assertLessEqual(lo, phat)
        self.assertGreaterEqual(hi, phat)

    def test_all_successes_interval_excludes_zero(self):
        lo, hi = sv.wilson_interval(20, 20)
        self.assertGreater(lo, 0.0)
        self.assertEqual(hi, 1.0)  # Wilson's upper bound is exactly 1 at p=1

    def test_more_data_narrows_the_interval(self):
        lo1, hi1 = sv.wilson_interval(5, 10)
        lo2, hi2 = sv.wilson_interval(500, 1000)
        self.assertLess(hi2 - lo2, hi1 - lo1)


class ExactMcNemarTests(unittest.TestCase):

    def test_no_discordant_pairs_is_certainty(self):
        self.assertEqual(sv.exact_mcnemar(0, 0), 1.0)

    def test_symmetric_in_fixed_and_broken(self):
        self.assertAlmostEqual(sv.exact_mcnemar(3, 7), sv.exact_mcnemar(7, 3))

    def test_matches_the_qwen_write_up_published_value(self):
        # docs/status/qwen-results.md section 3: "5 vs 0 discordant,
        # p = 0.0625" -- 2 * C(5,0) / 2**5 = 2/32 = 0.0625 by hand.
        self.assertAlmostEqual(sv.exact_mcnemar(0, 5), 0.0625, places=4)

    def test_large_lopsided_split_is_significant(self):
        self.assertLess(sv.exact_mcnemar(81, 3), 0.001)

    def test_even_split_is_not_significant(self):
        self.assertGreater(sv.exact_mcnemar(10, 10), 0.5)


class PairedMcNemarTests(unittest.TestCase):

    def setUp(self):
        # 5 alerts: arm A correct on 1,2; arm B correct on 2,3,4 ->
        # fixed (B right, A wrong) = {3,4} = 2; broken (A right, B
        # wrong) = {1} = 1.
        self.gt = {
            "u1": gt_row("u1", "Fuzzers"),
            "u2": gt_row("u2", "Fuzzers"),
            "u3": gt_row("u3", "Fuzzers"),
            "u4": gt_row("u4", "Fuzzers"),
            "u5": gt_row("u5", "Benign"),
        }
        self.arm_a = [
            verdict_row("u1", "true_positive", "Fuzzers"),
            verdict_row("u2", "true_positive", "Fuzzers"),
            verdict_row("u3", "false_positive", "none"),
            verdict_row("u4", "false_positive", "none"),
            verdict_row("u5", "false_positive", "none"),
        ]
        self.arm_b = [
            verdict_row("u1", "false_positive", "none"),
            verdict_row("u2", "true_positive", "Fuzzers"),
            verdict_row("u3", "true_positive", "Fuzzers"),
            verdict_row("u4", "true_positive", "Fuzzers"),
            verdict_row("u5", "false_positive", "none"),
        ]

    def test_verdict_field_fixed_and_broken_counts(self):
        result = sv.paired_mcnemar(self.arm_a, self.arm_b, self.gt, field="verdict")
        self.assertEqual(result["fixed"], 2)
        self.assertEqual(result["broken"], 1)
        self.assertAlmostEqual(result["p"], sv.exact_mcnemar(2, 1))

    def test_missing_uid_in_one_arm_is_skipped_not_errored(self):
        shorter_b = [r for r in self.arm_b if r["uid"] != "u4"]
        result = sv.paired_mcnemar(self.arm_a, shorter_b, self.gt, field="verdict")
        self.assertEqual(result["fixed"] + result["broken"], 2)  # u4 excluded


class ConfusionMatrixTests(unittest.TestCase):

    def test_counts_land_in_the_right_cells(self):
        gt = {
            "u1": gt_row("u1", "Fuzzers"),
            "u2": gt_row("u2", "Fuzzers"),
            "u3": gt_row("u3", "Exploits"),
        }
        verdicts = [
            verdict_row("u1", "true_positive", "Fuzzers"),
            verdict_row("u2", "true_positive", "none"),
            verdict_row("u3", "true_positive", "Fuzzers"),
        ]
        matrix = sv.confusion_matrix(verdicts, gt)
        self.assertEqual(matrix["Fuzzers"]["Fuzzers"], 1)
        self.assertEqual(matrix["Fuzzers"]["none"], 1)
        self.assertEqual(matrix["Exploits"]["Fuzzers"], 1)


class EscalationMetricsTests(unittest.TestCase):
    """Synthetic fixtures only -- no real run carries a `priority` field
    yet (BL-106, blocked); this is tested now so the code is correct
    and ready, per work-split.md's own instruction."""

    def test_perfect_priority_calls_score_1_and_1(self):
        gt = {
            "u1": gt_row("u1", "Exploits"),   # must-escalate
            "u2": gt_row("u2", "Fuzzers"),    # routine
        }
        verdicts = [
            verdict_row("u1", "true_positive", "Exploits", priority="escalate"),
            verdict_row("u2", "true_positive", "Fuzzers", priority="routine"),
        ]
        result = sv.escalation_metrics(verdicts, gt)
        self.assertEqual(result["escalation_precision"], 1.0)
        self.assertEqual(result["must_escalate_recall"], 1.0)
        self.assertEqual(result["scored"], 2)

    def test_rows_without_priority_field_are_skipped(self):
        gt = {"u1": gt_row("u1", "Exploits")}
        verdicts = [verdict_row("u1", "true_positive", "Exploits")]  # no priority
        result = sv.escalation_metrics(verdicts, gt)
        self.assertEqual(result["scored"], 0)

    def test_a_real_run_without_priority_scores_nothing(self):
        # Confirms the documented behaviour: every run collected so far
        # has no `priority` field, so this returns all-zero, not an error.
        gt = {"u1": gt_row("u1", "Exploits")}
        real_shaped_row = verdict_row("u1", "true_positive", "Exploits")
        result = sv.escalation_metrics([real_shaped_row], gt)
        self.assertEqual(result["tp"] + result["fp"] + result["fn"] + result["tn"], 0)

    def test_false_escalation_is_a_precision_miss(self):
        gt = {"u1": gt_row("u1", "Fuzzers")}  # routine
        verdicts = [verdict_row("u1", "true_positive", "Fuzzers", priority="escalate")]
        result = sv.escalation_metrics(verdicts, gt)
        self.assertEqual(result["fp"], 1)
        self.assertEqual(result["escalation_precision"], 0.0)


class TierSplitRecallTests(unittest.TestCase):

    def test_split_matches_hand_count(self):
        gt = {
            "u1": gt_row("u1", "Exploits"),       # escalate, caught
            "u2": gt_row("u2", "DoS"),             # escalate, missed
            "u3": gt_row("u3", "Fuzzers"),         # routine, caught
            "u4": gt_row("u4", "Benign"),          # excluded (not an attack)
        }
        verdicts = [
            verdict_row("u1", "true_positive", "Exploits"),
            verdict_row("u2", "false_positive", "none"),
            verdict_row("u3", "true_positive", "Fuzzers"),
            verdict_row("u4", "false_positive", "none"),
        ]
        result = sv.tier_split_recall(verdicts, gt)
        self.assertEqual(result["escalate"]["n"], 2)
        self.assertAlmostEqual(result["escalate"]["recall"], 0.5)
        self.assertEqual(result["routine"]["n"], 1)
        self.assertAlmostEqual(result["routine"]["recall"], 1.0)


class ColdStartSplitTests(unittest.TestCase):

    def test_splits_at_the_warmup_boundary_by_seq(self):
        gt = {f"u{i}": gt_row(f"u{i}", "Fuzzers") for i in range(5)}
        verdicts = [
            verdict_row(f"u{i}", "true_positive", "Fuzzers", seq=i)
            for i in range(5)
        ]
        result = sv.cold_start_split(verdicts, gt, warmup=2)
        self.assertEqual(result["cold"]["n"], 2)
        self.assertEqual(result["warm"]["n"], 3)

    def test_out_of_seq_order_input_is_still_sorted_first(self):
        gt = {f"u{i}": gt_row(f"u{i}", "Fuzzers") for i in range(3)}
        verdicts = [
            verdict_row("u2", "true_positive", "Fuzzers", seq=2),
            verdict_row("u0", "true_positive", "Fuzzers", seq=0),
            verdict_row("u1", "false_positive", "none", seq=1),
        ]
        result = sv.cold_start_split(verdicts, gt, warmup=1)
        # seq 0 is "cold"; it's a true_positive in a real-attack row.
        self.assertEqual(result["cold"]["tp"], 1)


class PairedBootstrapCiTests(unittest.TestCase):

    def test_identical_arms_collapse_the_ci_around_zero(self):
        gt = {f"u{i}": gt_row(f"u{i}", "Fuzzers") for i in range(20)}
        verdicts = [
            verdict_row(f"u{i}", "true_positive" if i % 2 else "false_positive",
                        "Fuzzers", seq=i)
            for i in range(20)
        ]
        result = sv.paired_bootstrap_ci(verdicts, verdicts, gt, metric="recall", n_boot=200)
        self.assertAlmostEqual(result["point"], 0.0)
        self.assertAlmostEqual(result["ci_lo"], 0.0, places=2)
        self.assertAlmostEqual(result["ci_hi"], 0.0, places=2)

    def test_point_estimate_matches_direct_computation(self):
        gt = {
            "u1": gt_row("u1", "Fuzzers"), "u2": gt_row("u2", "Fuzzers"),
        }
        arm_a = [verdict_row("u1", "false_positive", "none"),
                 verdict_row("u2", "false_positive", "none")]
        arm_b = [verdict_row("u1", "true_positive", "Fuzzers"),
                 verdict_row("u2", "false_positive", "none")]
        result = sv.paired_bootstrap_ci(arm_a, arm_b, gt, metric="recall", n_boot=50)
        expected = sv.score(arm_b, gt)["recall"] - sv.score(arm_a, gt)["recall"]
        self.assertAlmostEqual(result["point"], expected)


class ClusterBootstrapCiTests(unittest.TestCase):

    def test_identical_arms_collapse_the_ci_around_zero(self):
        gt = {f"u{i}": gt_row(f"u{i}", "Fuzzers") for i in range(20)}
        verdicts = [
            verdict_row(f"u{i}", "true_positive" if i % 2 else "false_positive",
                        "Fuzzers", dst_port=80 + (i % 5), seq=i)
            for i in range(20)
        ]
        result = sv.cluster_bootstrap_ci(verdicts, verdicts, gt, metric="recall", n_boot=200)
        self.assertAlmostEqual(result["point"], 0.0)
        self.assertAlmostEqual(result["ci_lo"], 0.0, places=2)
        self.assertAlmostEqual(result["ci_hi"], 0.0, places=2)

    def test_point_estimate_matches_direct_computation(self):
        gt = {
            "u1": gt_row("u1", "Fuzzers"), "u2": gt_row("u2", "Fuzzers"),
        }
        arm_a = [verdict_row("u1", "false_positive", "none", dst_port=80),
                 verdict_row("u2", "false_positive", "none", dst_port=81)]
        arm_b = [verdict_row("u1", "true_positive", "Fuzzers", dst_port=80),
                 verdict_row("u2", "false_positive", "none", dst_port=81)]
        result = sv.cluster_bootstrap_ci(arm_a, arm_b, gt, metric="recall", n_boot=50)
        expected = sv.score(arm_b, gt)["recall"] - sv.score(arm_a, gt)["recall"]
        self.assertAlmostEqual(result["point"], expected)

    def test_groups_by_detector_label_port_and_protocol(self):
        # Two alerts share a (detector_label, dst_port, protocol) key, so
        # they form one near-duplicate group; the third is a singleton.
        # n_groups should therefore be 2, not 3.
        gt = {f"u{i}": gt_row(f"u{i}", "Fuzzers") for i in range(3)}
        verdicts = [
            verdict_row("u0", "true_positive", "Fuzzers", detector_label="Fuzzers", dst_port=80, protocol=6),
            verdict_row("u1", "true_positive", "Fuzzers", detector_label="Fuzzers", dst_port=80, protocol=6),
            verdict_row("u2", "true_positive", "Fuzzers", detector_label="DoS", dst_port=53, protocol=17),
        ]
        result = sv.cluster_bootstrap_ci(verdicts, verdicts, gt, metric="recall", n_boot=20)
        self.assertEqual(result["n_groups"], 2)

    def test_clustering_widens_the_ci_when_a_group_drives_the_effect(self):
        # Build a case where the B-self "improvement" over Arm A is
        # concentrated entirely inside one large near-duplicate group.
        # A cluster bootstrap can drop that whole group in one resample;
        # a per-alert bootstrap never can. The cluster CI should
        # therefore be at least as wide as the per-alert one.
        gt = {}
        arm_a, arm_b = [], []
        # One big group of 12 alerts: Arm A misses all of them, B-self
        # catches all of them -- this is where the effect lives.
        for i in range(12):
            uid = f"group{i}"
            gt[uid] = gt_row(uid, "Fuzzers")
            arm_a.append(verdict_row(uid, "false_positive", "none",
                                      detector_label="Fuzzers", dst_port=80, protocol=6, seq=i))
            arm_b.append(verdict_row(uid, "true_positive", "Fuzzers",
                                      detector_label="Fuzzers", dst_port=80, protocol=6, seq=i))
        # 12 singleton alerts where both arms agree -- pure noise alerts
        # that add no signal either way.
        for i in range(12):
            uid = f"single{i}"
            gt[uid] = gt_row(uid, "Fuzzers")
            arm_a.append(verdict_row(uid, "true_positive", "Fuzzers",
                                      detector_label="DoS", dst_port=100 + i, protocol=6, seq=12 + i))
            arm_b.append(verdict_row(uid, "true_positive", "Fuzzers",
                                      detector_label="DoS", dst_port=100 + i, protocol=6, seq=12 + i))

        per_alert = sv.paired_bootstrap_ci(arm_a, arm_b, gt, metric="recall", n_boot=1000)
        clustered = sv.cluster_bootstrap_ci(arm_a, arm_b, gt, metric="recall", n_boot=1000)

        per_alert_width = per_alert["ci_hi"] - per_alert["ci_lo"]
        clustered_width = clustered["ci_hi"] - clustered["ci_lo"]
        self.assertGreaterEqual(clustered_width, per_alert_width)


class CostSummaryTests(unittest.TestCase):

    def test_means_and_sums_from_usage_fields(self):
        verdicts = [
            verdict_row("u1", "true_positive", "Fuzzers",
                        usage_prompt_tokens=100, usage_output_tokens=50,
                        usage_reasoning_tokens=10, usage_total_tokens=150),
            verdict_row("u2", "true_positive", "Fuzzers",
                        usage_prompt_tokens=200, usage_output_tokens=100,
                        usage_reasoning_tokens=20, usage_total_tokens=300),
        ]
        result = sv.cost_summary(verdicts)
        self.assertEqual(result["n_with_usage"], 2)
        self.assertAlmostEqual(result["mean_total_tokens"], 225.0)
        self.assertEqual(result["sum_total_tokens"], 450)

    def test_rows_without_usage_fields_are_skipped_not_zeroed(self):
        verdicts = [
            verdict_row("u1", "true_positive", "Fuzzers"),  # no usage_* at all
            verdict_row("u2", "true_positive", "Fuzzers", usage_total_tokens=300),
        ]
        result = sv.cost_summary(verdicts)
        self.assertEqual(result["n_with_usage"], 1)
        self.assertAlmostEqual(result["mean_total_tokens"], 300.0)


class ExistingScoreUnaffectedTests(unittest.TestCase):
    """Guards CLAUDE.md's protected-harness rule: nothing above the
    additions changed existing behaviour."""

    def test_score_function_still_returns_the_same_keys(self):
        gt = {"u1": gt_row("u1", "Fuzzers")}
        verdicts = [verdict_row("u1", "true_positive", "Fuzzers")]
        result = sv.score(verdicts, gt)
        for key in ("tp", "fp", "fn", "tn", "precision", "recall", "f1",
                    "cat_accuracy", "agreement", "mean_latency_ms"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()
