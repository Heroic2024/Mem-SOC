"""
Nearest-neighbour baseline for protocol v4 -- no LLM calls.

    python -m memsoc.triage.knn_baseline

Answers one question: how well does a plain 3-neighbour vote over true
labels name the attack family, on the same 165 alerts as the frozen
Gemma p3 runs? It is the non-LLM comparator B-oracle has to be read
against (BL-019, BL-160): B-oracle shows the model the true labels of
its 3 nearest earlier cases, so part of what it measures may be this
vote and not the model.

Definition (protocol v4 approval, 2026-10-29, item 6):

- Retrieval: the text-embedding retrieval the LLM runs actually used,
  read back from the B-oracle p3 log (`precedent_used`), not recomputed.
  Top-3, no similarity cutoff, earlier alerts only, exactly as the run
  saw them. B-self retrieved from the same alert texts; the check below
  confirms both logs name the same neighbours.
- Labels: the true attack family of each neighbour.
- Vote: the most common family among the neighbours. A tie goes to the
  nearest of the tied families.
- An alert with no neighbours (the first one) gets no prediction and is
  counted wrong.

Evaluation only. Ground truth is read through score_verdicts, the one
module allowed to open it; nothing in the triage path imports this. It
reads the frozen p3 artifacts and writes nothing.
"""

import json
import os
import sys
from collections import Counter

from memsoc import paths
from memsoc.triage import score_verdicts

K = 3

TAG = "gemma4-26b-p3"

RETRIEVAL_RUN = f"boracle-{TAG}"
CHECK_RUN = f"bself-{TAG}"

ARMS = (
    ("Arm A (memory off)", f"armA-{TAG}"),
    ("B-self (own verdicts)", f"bself-{TAG}"),
    ("B-oracle (true-label memory)", f"boracle-{TAG}"),
)


# ----------------------------------------------------------------------
# Reading the frozen p3 logs
# ----------------------------------------------------------------------

def _verdicts(run_id):

    rows = score_verdicts.read_verdicts(
        os.path.join(paths.run_dir(run_id), "triage_verdicts.jsonl")
    )

    return sorted(rows, key=lambda row: row["seq"])


def _case_alerts(run_id):
    """case_id -> the uid of the alert that case was written from."""

    case_alerts = {}

    with open(os.path.join(paths.memory_store(run_id), "cases.jsonl"), "r", encoding="utf-8") as f:

        for line in f:

            if line.strip():
                case = json.loads(line)
                case_alerts[case["case_id"]] = case["metadata"]["alert_id"]

    return case_alerts


def _neighbours(run_id):
    """uid -> neighbour uids, nearest first, as the run retrieved them."""

    case_alerts = _case_alerts(run_id)

    return {
        row["uid"]: [case_alerts[c] for c in row["precedent_used"].split(",") if c]
        for row in _verdicts(run_id)
    }


# ----------------------------------------------------------------------
# The vote
# ----------------------------------------------------------------------

def vote(labels):
    """Most common label; a tie goes to the earliest (nearest) of the tied."""

    if not labels:
        return None

    counts = Counter(labels)
    top = max(counts.values())

    return next(label for label in labels if counts[label] == top)


def _as_rows(order, predictions):
    """Predictions in the shape paired_mcnemar() reads."""

    return [
        {"uid": uid, "attack_category": predictions[uid] or ""}
        for uid in order
    ]


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():

    sys.stdout.reconfigure(encoding="utf-8")

    ground_truth = score_verdicts.read_ground_truth(paths.GROUND_TRUTH)

    def family(uid):
        return score_verdicts.expected_category(ground_truth[uid])

    retrieval_rows = _verdicts(RETRIEVAL_RUN)
    order = [row["uid"] for row in retrieval_rows]
    seq = {uid: i for i, uid in enumerate(order)}

    neighbours = _neighbours(RETRIEVAL_RUN)

    # Earlier alerts only, at most K, and the same neighbours in B-self.
    for uid in order:
        assert len(neighbours[uid]) <= K, uid
        assert all(seq[n] < seq[uid] for n in neighbours[uid]), uid

    check = _neighbours(CHECK_RUN)
    same = sum(check.get(uid) == neighbours[uid] for uid in order)

    knn = {uid: vote([family(n) for n in neighbours[uid]][:K]) for uid in order}
    knn_rows = _as_rows(order, knn)

    detector_rows = [
        {"uid": row["uid"], "attack_category": row["detector_label"]}
        for row in retrieval_rows
    ]

    methods = [
        (f"kNN-{K} vote, true labels (no LLM)", knn_rows),
        ("Detector alone (no LLM)", detector_rows),
    ]

    for name, run_id in ARMS:
        methods.append((name, _verdicts(run_id)))

    n = len(order)

    print(f"Nearest-neighbour baseline, {n} alerts of {TAG}")
    print(f"Retrieval from {RETRIEVAL_RUN}; {CHECK_RUN} retrieved the same neighbours on {same} of {n}")
    print(f"Alerts with no neighbour (counted wrong): {sum(1 for uid in order if not neighbours[uid])}")
    print()
    print("| Method | Family correct | Accuracy | 95% CI | kNN right, other wrong | Other right, kNN wrong | McNemar p |")
    print("|---|---:|---:|---:|---:|---:|---:|")

    for name, rows in methods:

        by_uid = {row["uid"]: row for row in rows}
        assert set(by_uid) == set(order), name

        correct = sum(by_uid[uid]["attack_category"] == family(uid) for uid in order)
        lo, hi = score_verdicts.wilson_interval(correct, n)

        if rows is knn_rows:
            paired = "| — | — | — |"
        else:
            test = score_verdicts.paired_mcnemar(rows, knn_rows, ground_truth, field="category")
            paired = f"| {test['fixed']} | {test['broken']} | {test['p']:.2g} |"

        print(f"| {name} | {correct}/{n} | {correct / n:.1%} | {lo:.1%}–{hi:.1%} {paired}")


if __name__ == "__main__":
    main()
