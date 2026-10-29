"""
Phase 1 scoring harness.

This is the ONLY module in the triage path that opens ground_truth.csv.
Ground-truth labels are the evaluation oracle (PROJECT_BRIEF.md
section 5): the detector produces alerts, the LLM produces verdicts, and
ground truth scores those verdicts after the fact. Nothing upstream --
triage_prompt.py, triage_runner.py, llm_client.py -- can see this file,
and that separation is what keeps the Arm A vs Arm B comparison valid.

No LLM is involved here. Every number is plain Python aggregation over
triage_verdicts.jsonl joined to ground_truth.csv on uid, in the same
spirit as stats_engine.py.

Three distinct comparisons are reported, and conflating them is the
easiest mistake to make with these numbers:

  1. LLM verdict     vs ground truth   -- the experiment
  2. LLM category    vs ground truth   -- the experiment (Option A primary)
  3. LLM category    vs detector label -- NOT a correctness measure; it
                                          detects the LLM echoing the
                                          detector instead of reasoning

Every metric here is computed for whichever arm's verdict file is read.
Comparing arms is a matter of running this against each and diffing --
the metric definitions do not change between arms.

Usage (from the repo root, with src/ on PYTHONPATH):
    python -m memsoc.triage.score_verdicts
    python -m memsoc.triage.score_verdicts --verdicts path/to/other.jsonl
    python -m memsoc.triage.score_verdicts --show-errors
"""

import argparse
import csv
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict

from memsoc.triage import config

# Verdict rows written before prompt_variant existed were produced by the
# first prompt wording (BL-120).
LEGACY_PROMPT_VARIANT = "label-hypothesis-v1"


def read_ground_truth(path):

    with open(path, "r", encoding="utf-8") as f:
        return {row["uid"]: row for row in csv.DictReader(f)}


def read_verdicts(path):

    rows = []

    with open(path, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return rows


def expected_category(gt_row):
    """
    The category the LLM should have named for this flow.

    'none' for genuinely benign traffic -- that is the case-schema value
    for "the analyst judged this not an attack", so an LLM that
    correctly dismisses a false alarm scores as correct here rather than
    being penalised for not naming a family.
    """

    attack = gt_row["attack"]

    return "none" if attack == "Benign" else attack


def score(verdicts, ground_truth):

    joined = []
    unmatched = []

    for row in verdicts:

        gt_row = ground_truth.get(row["uid"])

        if gt_row is None:
            unmatched.append(row["uid"])
            continue

        joined.append((row, gt_row))

    # ---- 1. Verdict vs ground truth -------------------------------
    #
    # true_positive  = "this alert is genuinely malicious"  -> escalate
    # false_positive = "this alert is a false alarm"        -> dismiss
    # inconclusive   = no call; excluded from precision/recall and
    #                  reported separately rather than silently folded
    #                  into one of the decisive classes.
    tp = fp = fn = tn = 0
    inconclusive = 0

    for row, gt_row in joined:

        truly_attack = gt_row["attack"] != "Benign"
        verdict = row["verdict"]

        if verdict == "inconclusive":
            inconclusive += 1
        elif verdict == "true_positive":
            if truly_attack:
                tp += 1
            else:
                fp += 1
        elif verdict == "false_positive":
            if truly_attack:
                fn += 1
            else:
                tn += 1

    decisive = tp + fp + fn + tn

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    # ---- 2. Category vs ground truth ------------------------------
    cat_correct = 0
    det_correct = 0
    cat_errors = Counter()

    for row, gt_row in joined:

        want = expected_category(gt_row)

        if row["attack_category"] == want:
            cat_correct += 1
        else:
            cat_errors[(want, row["attack_category"])] += 1

        if row["detector_label"] == want:
            det_correct += 1

    n = len(joined)
    cat_accuracy = cat_correct / n if n else 0.0
    det_accuracy = det_correct / n if n else 0.0

    # ---- 3. Category vs detector (echo check) ---------------------
    agreed = sum(
        1 for row, _ in joined if row["attack_category"] == row["detector_label"]
    )
    agreement = agreed / n if n else 0.0

    # ---- 4. Consistency across near-duplicate alerts --------------
    #
    # Near-duplicate = same detector label, destination port and
    # protocol. Memory is expected to make the LLM more self-consistent
    # on these; Arm A has no mechanism for it, so this is the number
    # Arm B should move.
    groups = defaultdict(list)

    for row, _ in joined:
        key = (row["detector_label"], row["dst_port"], row["protocol"])
        groups[key].append(row)

    multi = {k: v for k, v in groups.items() if len(v) > 1}

    consistent_verdict = sum(
        1 for rows in multi.values()
        if len({r["verdict"] for r in rows}) == 1
    )
    consistent_category = sum(
        1 for rows in multi.values()
        if len({r["attack_category"] for r in rows}) == 1
    )

    latencies = [r["latency_ms"] for r, _ in joined if r.get("latency_ms")]

    return {
        "n": n,
        "unmatched": unmatched,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "inconclusive": inconclusive,
        "decisive": decisive,
        "precision": precision, "recall": recall, "f1": f1,
        "cat_accuracy": cat_accuracy,
        "det_accuracy": det_accuracy,
        "cat_errors": cat_errors,
        "agreement": agreement,
        "groups_multi": len(multi),
        "consistent_verdict": consistent_verdict,
        "consistent_category": consistent_category,
        "mean_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
    }


# ----------------------------------------------------------------------
# Additions below this line (2026-10-23): Wilson intervals, exact
# McNemar, a real confusion matrix, the B1 escalation metric, and four
# further extensions. Additive only, per CLAUDE.md's protected-harness
# rule -- nothing above this line changed shape or behaviour, and every
# existing metric's value is unchanged by anything below. See
# docs/research-paper/README.md (the Person 3 execution plan) for why
# each of these exists.
# ----------------------------------------------------------------------

Z_95 = 1.959963984540054  # two-sided 95% normal quantile


def wilson_interval(successes, n, z=Z_95):
    """
    95% Wilson score interval for a proportion. statistics.NormalDist
    is available (z above is its inv_cdf(0.975), computed once rather
    than imported as a dependency), no scipy/statsmodels, per
    work-split.md. Returns (lo, hi); (0.0, 0.0) if n == 0.
    """

    if n == 0:
        return (0.0, 0.0)

    phat = successes / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))

    return ((center - margin) / denom, (center + margin) / denom)


def exact_mcnemar(fixed, broken):
    """
    Exact two-sided McNemar p-value from the discordant pair counts
    (fixed = B correct where A wasn't; broken = the reverse), via
    math.comb only -- scipy/statsmodels are the rejected alternatives
    (work-split.md). p = 2 * P(X <= min(fixed, broken)) for
    X ~ Binomial(fixed + broken, 0.5), capped at 1.0.
    """

    n = fixed + broken

    if n == 0:
        return 1.0

    k = min(fixed, broken)
    cdf = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)

    return min(1.0, 2 * cdf)


def _by_uid(verdicts):
    return {row["uid"]: row for row in verdicts}


def _correct_verdict(row, gt_row):
    """True if this row's verdict matches ground truth (TP or TN)."""

    truly_attack = gt_row["attack"] != "Benign"

    if row["verdict"] == "true_positive":
        return truly_attack
    if row["verdict"] == "false_positive":
        return not truly_attack

    return False  # inconclusive is never "correct"


def _correct_category(row, gt_row):
    return row["attack_category"] == expected_category(gt_row)


def paired_mcnemar(verdicts_a, verdicts_b, ground_truth, field="verdict"):
    """
    Paired exact McNemar test between two arms over their shared
    alerts (joined on uid). `field`: "verdict" (correct escalate/
    dismiss call) or "category" (correct attack family). Returns
    fixed/broken counts and the exact p-value. This is what the Gemma
    and Groq p1 write-ups each computed with a one-off script before
    this function existed -- now reusable and testable in one place.
    """

    correct_fn = _correct_category if field == "category" else _correct_verdict

    a_by_uid, b_by_uid = _by_uid(verdicts_a), _by_uid(verdicts_b)
    fixed = broken = 0

    for uid, a_row in a_by_uid.items():

        b_row = b_by_uid.get(uid)
        gt_row = ground_truth.get(uid)

        if b_row is None or gt_row is None:
            continue

        a_ok = correct_fn(a_row, gt_row)
        b_ok = correct_fn(b_row, gt_row)

        if b_ok and not a_ok:
            fixed += 1
        elif a_ok and not b_ok:
            broken += 1

    return {
        "fixed": fixed,
        "broken": broken,
        "p": exact_mcnemar(fixed, broken),
    }


def confusion_matrix(verdicts, ground_truth):
    """
    A real category confusion matrix: matrix[expected][predicted] =
    count. BL-040 names the gap this fills -- score()'s own cat_errors
    is a flat Counter of (expected, predicted) pairs that disagree
    only; this is the full matrix, diagonal included.
    """

    matrix = defaultdict(Counter)

    for row in verdicts:

        gt_row = ground_truth.get(row["uid"])

        if gt_row is None:
            continue

        matrix[expected_category(gt_row)][row["attack_category"]] += 1

    return {k: dict(v) for k, v in matrix.items()}


# The B1 tier split (decisions.md B1, tracked as BL-105): families that
# warrant waking an analyst versus routine scanning/probing noise.
MUST_ESCALATE_FAMILIES = {"Worms", "Backdoor", "Shellcode", "Exploits", "DoS", "Generic"}
ROUTINE_FAMILIES = {"Reconnaissance", "Analysis", "Fuzzers"}


def escalation_metrics(verdicts, ground_truth):
    """
    Escalation precision + must-escalate recall -- the B1 headline
    metric. Needs a `priority` field ("escalate"/"routine") on each
    verdict row, distinct from `verdict` and `attack_category`; no
    real run's schema carries it yet (BL-106, blocked on sign-off,
    since the prompt template is a protected component). Rows without
    a `priority` field are skipped, so this returns all-zero on every
    run collected so far -- it exists to be tested against synthetic
    fixtures (tests/test_score_verdicts.py) now, and run for real the
    moment BL-106 unblocks, per work-split.md's own instruction that
    this is "developed against synthetic verdict files long before a
    real run exists."
    """

    tp = fp = fn = tn = 0

    for row in verdicts:

        gt_row = ground_truth.get(row["uid"])
        said = row.get("priority")

        if gt_row is None or said not in ("escalate", "routine"):
            continue

        want = expected_category(gt_row)
        true_tier = "escalate" if want in MUST_ESCALATE_FAMILIES else "routine"

        if said == "escalate" and true_tier == "escalate":
            tp += 1
        elif said == "escalate" and true_tier == "routine":
            fp += 1
        elif said == "routine" and true_tier == "escalate":
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    return {
        "escalation_precision": precision,
        "must_escalate_recall": recall,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "scored": tp + fp + fn + tn,
    }


def tier_split_recall(verdicts, ground_truth):
    """
    PROXY for the B1 escalation metric above -- not a substitute for
    it. Uses only the existing `verdict` field (not a model-emitted
    `priority`), split by the B1 tier mapping on the *ground-truth*
    family. Answers a narrower question: does the model still catch
    real attacks, broken out by whether that attack was must-escalate
    or routine? It does not test whether the model can judge severity
    itself -- that is what escalation_metrics() above is for, once
    BL-106 unblocks. Computable today on every real run.
    """

    buckets = {"escalate": {"tp": 0, "fn": 0}, "routine": {"tp": 0, "fn": 0}}

    for row in verdicts:

        gt_row = ground_truth.get(row["uid"])

        if gt_row is None or gt_row["attack"] == "Benign":
            continue  # the tier split is only defined over real attacks

        want = expected_category(gt_row)
        tier = "escalate" if want in MUST_ESCALATE_FAMILIES else "routine"

        if row["verdict"] == "true_positive":
            buckets[tier]["tp"] += 1
        elif row["verdict"] == "false_positive":
            buckets[tier]["fn"] += 1

    out = {}

    for tier, c in buckets.items():
        total = c["tp"] + c["fn"]
        out[tier] = {"recall": c["tp"] / total if total else 0.0, "n": total, **c}

    return out


def cold_start_split(verdicts, ground_truth, warmup=10):
    """
    score() over the first `warmup` alerts (by seq, i.e. stream order)
    versus the rest. Formalizes decisions.md C7's own recommendation --
    "report the early alerts and the later alerts as two separate
    figures instead" -- as a reusable function instead of a hand-built
    chart per write-up.
    """

    ordered = sorted(verdicts, key=lambda r: r["seq"])

    return {
        "cold": score(ordered[:warmup], ground_truth),
        "warm": score(ordered[warmup:], ground_truth),
    }


def paired_bootstrap_ci(verdicts_a, verdicts_b, ground_truth, metric="recall",
                         n_boot=2000, seed=20261023):
    """
    95% CI on the paired difference (arm B's metric minus arm A's),
    via bootstrap resampling of the shared alert set, with
    replacement. McNemar says a gap is statistically real; this says
    how big it reliably is. `metric`: any key score() returns, e.g.
    "recall" or "cat_accuracy". `seed` makes this reproducible.
    """

    rng = random.Random(seed)
    a_by_uid, b_by_uid = _by_uid(verdicts_a), _by_uid(verdicts_b)
    uids = [u for u in a_by_uid if u in b_by_uid and u in ground_truth]

    point = (
        score(list(b_by_uid.values()), ground_truth)[metric]
        - score(list(a_by_uid.values()), ground_truth)[metric]
    )

    if not uids:
        return {"point": point, "ci_lo": point, "ci_hi": point, "n_boot": 0}

    diffs = []

    for _ in range(n_boot):

        sample = rng.choices(uids, k=len(uids))
        gt_sub = {u: ground_truth[u] for u in set(sample)}

        sa = score([a_by_uid[u] for u in sample], gt_sub)[metric]
        sb = score([b_by_uid[u] for u in sample], gt_sub)[metric]

        diffs.append(sb - sa)

    diffs.sort()
    lo = diffs[int(0.025 * n_boot)]
    hi = diffs[min(n_boot - 1, int(0.975 * n_boot))]

    return {"point": point, "ci_lo": lo, "ci_hi": hi, "n_boot": n_boot}


def cluster_bootstrap_ci(verdicts_a, verdicts_b, ground_truth, metric="recall",
                          n_boot=2000, seed=20261023):
    """
    95% CI on the paired difference (arm B's metric minus arm A's), via a
    CLUSTER bootstrap that resamples whole near-duplicate groups --
    (detector_label, dst_port, protocol), the same key score() uses for
    its own consistency check -- instead of individual alerts.

    paired_bootstrap_ci() treats every alert as an independent draw. In a
    memory arm that assumption is shaky: alerts inside the same
    near-duplicate group stop being independent once memory starts
    repeating a stored label across them, so the group, not the alert,
    is closer to the true unit of evidence. This resamples groups with
    replacement (singleton groups behave like an ordinary alert; a
    multi-alert group is kept or dropped as a block), which is the
    standard fix for clustered data and is expected to widen the CI and
    produce a less extreme implied p-value than the per-alert version
    -- exactly the correction a reviewer would ask for before trusting a
    McNemar p-value computed as if every alert were independent.
    """

    rng = random.Random(seed)
    a_by_uid, b_by_uid = _by_uid(verdicts_a), _by_uid(verdicts_b)
    uids = [u for u in a_by_uid if u in b_by_uid and u in ground_truth]

    point = (
        score(list(b_by_uid.values()), ground_truth)[metric]
        - score(list(a_by_uid.values()), ground_truth)[metric]
    )

    if not uids:
        return {"point": point, "ci_lo": point, "ci_hi": point,
                "n_boot": 0, "n_groups": 0, "p_empirical": None}

    groups = defaultdict(list)
    for u in uids:
        row = a_by_uid[u]
        key = (row["detector_label"], row["dst_port"], row["protocol"])
        groups[key].append(u)
    group_keys = list(groups.keys())

    diffs = []

    for _ in range(n_boot):

        sampled_groups = rng.choices(group_keys, k=len(group_keys))
        sample = [u for key in sampled_groups for u in groups[key]]
        gt_sub = {u: ground_truth[u] for u in set(sample)}

        sa = score([a_by_uid[u] for u in sample], gt_sub)[metric]
        sb = score([b_by_uid[u] for u in sample], gt_sub)[metric]

        diffs.append(sb - sa)

    diffs.sort()
    lo = diffs[int(0.025 * n_boot)]
    hi = diffs[min(n_boot - 1, int(0.975 * n_boot))]

    # Two-sided empirical p-value: the share of resamples whose
    # difference lands on the opposite side of zero from the point
    # estimate, doubled. This is a test of sign, not of magnitude, and
    # is comparable in spirit to the per-alert McNemar p-value it is
    # meant to check.
    if point >= 0:
        p_empirical = 2 * min(sum(1 for d in diffs if d <= 0) / n_boot, 0.5)
    else:
        p_empirical = 2 * min(sum(1 for d in diffs if d >= 0) / n_boot, 0.5)

    return {
        "point": point, "ci_lo": lo, "ci_hi": hi, "n_boot": n_boot,
        "n_groups": len(group_keys), "p_empirical": p_empirical,
    }


def cost_summary(verdicts):
    """
    Token usage per verdict, from the usage_* fields protocol_run.py
    already writes into every row -- no schema change needed. Rows
    without usage data (e.g. a non-protocol or pre-BL-121 run) are
    silently skipped, so n_with_usage may be less than len(verdicts).
    """

    def collect(key):
        return [r[key] for r in verdicts if r.get(key) is not None]

    prompt_tokens = collect("usage_prompt_tokens")
    output_tokens = collect("usage_output_tokens")
    reasoning_tokens = collect("usage_reasoning_tokens")
    total_tokens = collect("usage_total_tokens")

    def mean(xs):
        return statistics.fmean(xs) if xs else 0.0

    return {
        "n_with_usage": len(total_tokens),
        "mean_prompt_tokens": mean(prompt_tokens),
        "mean_output_tokens": mean(output_tokens),
        "mean_reasoning_tokens": mean(reasoning_tokens),
        "mean_total_tokens": mean(total_tokens),
        "sum_total_tokens": sum(total_tokens),
    }


def prompt_variants(verdicts):
    """The prompt wordings present in a verdict file (BL-120)."""

    return sorted({row.get("prompt_variant", LEGACY_PROMPT_VARIANT) for row in verdicts})


def report(s, arm, show_errors, prompt_variant=LEGACY_PROMPT_VARIANT):

    print(f"\n{'=' * 62}")
    print(f"  Phase 1 scoring -- arm: {arm} -- {s['n']} alerts scored")
    print(f"  prompt variant: {prompt_variant}  (compare arms only within one variant)")
    print("=" * 62)

    if s["unmatched"]:
        print(f"\n!! {len(s['unmatched'])} verdicts had no ground-truth row "
              f"and were excluded:")
        for uid in s["unmatched"][:10]:
            print(f"     {uid}")
        print("   Every alert should join. Investigate before trusting "
              "these numbers.")

    print("\n1. VERDICT vs GROUND TRUTH  (the experiment)")
    print("   escalate = true_positive, dismiss = false_positive\n")
    print(f"   TP {s['tp']:>4}   correctly escalated a real attack")
    print(f"   FP {s['fp']:>4}   escalated benign traffic  <-- false-positive volume")
    print(f"   FN {s['fn']:>4}   dismissed a real attack   <-- most costly error")
    print(f"   TN {s['tn']:>4}   correctly dismissed a false alarm")
    print(f"   inconclusive {s['inconclusive']}  (excluded from the rates below)")
    print(f"\n   precision {s['precision']:.3f}   recall {s['recall']:.3f}   "
          f"F1 {s['f1']:.3f}   over {s['decisive']} decisive verdicts")

    print("\n2. CATEGORY vs GROUND TRUTH  (Option A primary metric)\n")
    delta = s["cat_accuracy"] - s["det_accuracy"]
    arrow = "better than" if delta > 0 else ("worse than" if delta < 0 else "level with")
    print(f"   LLM category accuracy      {s['cat_accuracy']:.3f}")
    print(f"   detector, same alerts      {s['det_accuracy']:.3f}")
    print(f"   difference                 {delta:+.3f}  ({arrow} the detector)")

    if s["cat_errors"] and show_errors:
        print("\n   category errors (expected -> LLM said):")
        for (want, got), count in s["cat_errors"].most_common(15):
            print(f"     {want:<16} -> {got:<16} {count}")

    print("\n3. CATEGORY vs DETECTOR  (echo check -- NOT a correctness measure)\n")
    print(f"   agreement with detector    {s['agreement']:.3f}")

    if s["agreement"] >= 0.98:
        print("\n   WARNING: near-total agreement. The LLM is most likely "
              "copying the\n   detector's label rather than reasoning about "
              "the flow. Category\n   accuracy above is then just the "
              "detector's accuracy wearing a\n   different hat, and Arm B "
              "cannot beat Arm A on it. Fix the prompt.")
    elif s["agreement"] <= 0.5:
        print("\n   NOTE: the LLM overrules the detector on more than half of "
              "alerts.\n   Check section 2 -- if accuracy did not improve, it "
              "is disagreeing\n   without being more right, which is worse "
              "than echoing.")

    print("\n4. CONSISTENCY across near-duplicate alerts")
    print("   grouped by (detector_label, dst_port, protocol), groups of 2+\n")

    if s["groups_multi"]:
        cv = s["consistent_verdict"] / s["groups_multi"]
        cc = s["consistent_category"] / s["groups_multi"]
        print(f"   groups                     {s['groups_multi']}")
        print(f"   uniform verdict            {s['consistent_verdict']} "
              f"({cv:.1%})")
        print(f"   uniform category           {s['consistent_category']} "
              f"({cc:.1%})")
    else:
        print("   no near-duplicate groups found")

    print(f"\n5. COST\n\n   mean latency  {s['mean_latency_ms']:.0f} ms")
    print(f"   LLM requests  {s['n']}")
    print()


def main():

    parser = argparse.ArgumentParser(description="Phase 1 verdict scoring")
    parser.add_argument(
        "--verdicts", default=str(config.VERDICTS_PATH),
        help="Verdict file to score (default: this run's Arm A output)"
    )
    parser.add_argument(
        "--show-errors", action="store_true",
        help="List the category confusions, not just the accuracy"
    )
    args = parser.parse_args()

    if not config.GROUND_TRUTH_PATH.exists():
        print(f"Ground truth not found: {config.GROUND_TRUTH_PATH}",
              file=sys.stderr)
        sys.exit(1)

    verdicts = read_verdicts(args.verdicts)

    if not verdicts:
        print(
            f"No verdicts in {args.verdicts}.\n"
            "Run triage_runner.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Verdicts from different prompt wordings are not comparable, so a
    # file that mixes them is refused rather than scored as one arm.
    variants = prompt_variants(verdicts)

    if len(variants) > 1:
        print(
            f"{args.verdicts} mixes prompt variants {variants}.\n"
            "Verdicts from different prompt wordings cannot be scored "
            "together (BL-120).",
            file=sys.stderr,
        )
        sys.exit(1)

    ground_truth = read_ground_truth(config.GROUND_TRUTH_PATH)

    arms = {row.get("arm", "unknown") for row in verdicts}
    arm = arms.pop() if len(arms) == 1 else f"MIXED {sorted(arms)}"

    report(score(verdicts, ground_truth), arm, args.show_errors, variants[0])


if __name__ == "__main__":
    main()
