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

Usage:
    python score_verdicts.py
    python score_verdicts.py --verdicts path/to/other_verdicts.jsonl
    python score_verdicts.py --show-errors
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict

import config

# The detector's own category accuracy over the same alerts, measured
# before any LLM ran. Reported alongside the LLM's so the comparison is
# visible rather than something the reader has to remember.
DETECTOR_CATEGORY_BASELINE = 0.881


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


def report(s, arm, show_errors):

    print(f"\n{'=' * 62}")
    print(f"  Phase 1 scoring -- arm: {arm} -- {s['n']} alerts scored")
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
    print(f"   pre-run detector baseline  {DETECTOR_CATEGORY_BASELINE:.3f}")

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

    ground_truth = read_ground_truth(config.GROUND_TRUTH_PATH)

    arms = {row.get("arm", "unknown") for row in verdicts}
    arm = arms.pop() if len(arms) == 1 else f"MIXED {sorted(arms)}"

    report(score(verdicts, ground_truth), arm, args.show_errors)


if __name__ == "__main__":
    main()
