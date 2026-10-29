"""
Builds the Static section's JSON bundles from already-computed results.
Run once (and again any time the underlying data changes):

    python static_export.py

Nothing here calls an LLM or does new experimentation -- it only
re-aggregates artifacts/runs/*/triage_verdicts.jsonl through the
project's own score_verdicts.py, so every number here is traceable back
to that one scoring function.
"""

import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(BACKEND_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from memsoc.triage import score_verdicts as sv  # noqa: E402

ARTIFACTS = os.path.join(REPO_ROOT, "artifacts")
RUNS_DIR = os.path.join(ARTIFACTS, "runs")
OUT_DIR = os.path.join(BACKEND_DIR, "static_data")
os.makedirs(OUT_DIR, exist_ok=True)

GT = sv.read_ground_truth(os.path.join(ARTIFACTS, "ground_truth.csv"))

MODELS = {
    "gemma": {
        "label": "Gemma 4 26B",
        "arms": {
            "A": "armA-gemma4-26b-p3",
            "bself": "bself-gemma4-26b-p3",
            "boracle": "boracle-gemma4-26b-p3",
        },
    },
    "gptoss": {
        "label": "gpt-oss-20b",
        "arms": {
            "A": "armA-gptoss20b-p1",
            "bself": "bself-gptoss20b-p1",
            "boracle": "boracle-gptoss20b-p1",
        },
    },
}


def load_arm(run_id):
    path = os.path.join(RUNS_DIR, run_id, "triage_verdicts.jsonl")
    return sv.read_verdicts(path)


def resolve_precedents(record, bself_family_by_seq, oracle_true_family_by_seq):
    used = record.get("precedent_used") or ""
    out = []
    for cid in used.split(","):
        cid = cid.strip()
        m = re.match(r"(.+):(\d+)$", cid)
        if not m:
            continue
        run_id, seq_s = m.group(1), int(m.group(2))
        if run_id.startswith("bself"):
            out.append(bself_family_by_seq.get(seq_s))
        elif run_id.startswith("boracle"):
            out.append(oracle_true_family_by_seq.get(seq_s))
    return out


def copy_rate_stats(armA, bself, boracle, gt):
    armA_by_seq = {r["seq"]: r for r in armA}
    bself_by_seq = {r["seq"]: r for r in bself}
    boracle_by_seq = {r["seq"]: r for r in boracle}
    bself_family_by_seq = {s: r["attack_category"] for s, r in bself_by_seq.items()}
    oracle_true_family_by_seq = {s: gt.get(r["uid"], {}).get("attack") for s, r in boracle_by_seq.items()}

    n = 0
    plurality_match = 0
    armA_counterfactual_match = 0
    shared_family_alerts = 0
    shared_family_copied = 0
    for r in bself:
        fams = [f for f in resolve_precedents(r, bself_family_by_seq, oracle_true_family_by_seq) if f]
        if not fams:
            continue
        n += 1
        counts = Counter(fams)
        plurality_fam, _ = counts.most_common(1)[0]
        if r["attack_category"] == plurality_fam:
            plurality_match += 1
        a = armA_by_seq.get(r["seq"])
        if a and a["attack_category"] == plurality_fam:
            armA_counterfactual_match += 1
        if len(fams) == 3 and len(set(fams)) == 1:
            shared_family_alerts += 1
            if r["attack_category"] == fams[0]:
                shared_family_copied += 1
    return {
        "n_with_precedent": n,
        "plurality_match": plurality_match,
        "plurality_match_pct": round(100 * plurality_match / n, 1) if n else None,
        "armA_counterfactual_match": armA_counterfactual_match,
        "armA_counterfactual_pct": round(100 * armA_counterfactual_match / n, 1) if n else None,
        "shared_family_alerts": shared_family_alerts,
        "shared_family_copied": shared_family_copied,
        "shared_family_copy_pct": round(100 * shared_family_copied / shared_family_alerts, 1) if shared_family_alerts else None,
    }


def per_model_bundle(key, cfg):
    arms = {name: load_arm(run_id) for name, run_id in cfg["arms"].items()}
    gt_simple = {uid: row["attack"] for uid, row in GT.items()}

    bundle = {"model": key, "label": cfg["label"], "arms": {}}

    for arm_name, verdicts in arms.items():
        s = sv.score(verdicts, GT)
        bundle["arms"][arm_name] = {
            "n": s["n"],
            "recall": round(s["recall"], 4),
            "cat_accuracy": round(s["cat_accuracy"], 4),
            "agreement": round(s["agreement"], 4),
            "tp": s["tp"], "fp": s["fp"], "fn": s["fn"], "tn": s["tn"],
            "inconclusive": s["inconclusive"],
            "recall_wilson": sv.wilson_interval(s["tp"], s["tp"] + s["fn"]),
            "cat_accuracy_wilson": sv.wilson_interval(
                round(s["cat_accuracy"] * s["n"]), s["n"]
            ),
        }

    if "A" in arms and "bself" in arms:
        mcnemar_recall = sv.paired_mcnemar(arms["A"], arms["bself"], GT, field="verdict")
        mcnemar_cat = sv.paired_mcnemar(arms["A"], arms["bself"], GT, field="category")
        pb_recall = sv.paired_bootstrap_ci(arms["A"], arms["bself"], GT, metric="recall")
        pb_cat = sv.paired_bootstrap_ci(arms["A"], arms["bself"], GT, metric="cat_accuracy")
        cb_recall = sv.cluster_bootstrap_ci(arms["A"], arms["bself"], GT, metric="recall")
        cb_cat = sv.cluster_bootstrap_ci(arms["A"], arms["bself"], GT, metric="cat_accuracy")
        bundle["bself_vs_armA"] = {
            "recall": {"mcnemar": mcnemar_recall, "per_alert_bootstrap": pb_recall, "cluster_bootstrap": cb_recall},
            "cat_accuracy": {"mcnemar": mcnemar_cat, "per_alert_bootstrap": pb_cat, "cluster_bootstrap": cb_cat},
        }

    if "A" in arms and "boracle" in arms:
        bundle["boracle_vs_armA"] = {
            "recall_mcnemar": sv.paired_mcnemar(arms["A"], arms["boracle"], GT, field="verdict"),
            "cat_accuracy_mcnemar": sv.paired_mcnemar(arms["A"], arms["boracle"], GT, field="category"),
        }

    if "bself" in arms and "boracle" in arms:
        bundle["copy_rate"] = copy_rate_stats(arms["A"], arms["bself"], arms["boracle"], GT)

    # Consistency on near-duplicate groups, per arm.
    bundle["consistency"] = {}
    for arm_name, verdicts in arms.items():
        s = sv.score(verdicts, GT)
        bundle["consistency"][arm_name] = {
            "groups_multi": s["groups_multi"],
            "consistent_verdict": s["consistent_verdict"],
            "consistent_category": s["consistent_category"],
        }

    return bundle


def main():
    cross_model = {"models": {}}
    for key, cfg in MODELS.items():
        bundle = per_model_bundle(key, cfg)
        with open(os.path.join(OUT_DIR, f"model_{key}.json"), "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)
        cross_model["models"][key] = {
            "label": cfg["label"],
            "arms": bundle["arms"],
        }
        print(f"wrote model_{key}.json")

    with open(os.path.join(OUT_DIR, "cross_model.json"), "w", encoding="utf-8") as f:
        json.dump(cross_model, f, indent=2)
    print("wrote cross_model.json")


if __name__ == "__main__":
    main()
