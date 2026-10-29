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


def mean_latency(verdicts):
    vals = [r["latency_ms"] for r in verdicts if r.get("latency_ms") is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def family_breakdown(verdicts):
    """Counts, by attack family, of alerts this arm correctly escalated
    (verdict true_positive). Used for the donut chart."""
    counts = Counter(
        r["attack_category"] for r in verdicts
        if r["verdict"] == "true_positive"
    )
    return dict(counts.most_common())


def confidence_histogram(verdicts, bucket_edges=(0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.01)):
    """Histogram of confidence values among correct catches (verdict ==
    true_positive), bucketed for the confidence chart."""
    labels = ["0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-0.95", "0.95-1.0"]
    counts = [0] * len(labels)
    for r in verdicts:
        if r["verdict"] != "true_positive":
            continue
        c = r.get("confidence")
        if c is None:
            continue
        for i in range(len(bucket_edges) - 1):
            if bucket_edges[i] <= c < bucket_edges[i + 1]:
                counts[i] += 1
                break
    return {"labels": labels, "counts": counts}


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
            "mean_latency_ms": mean_latency(verdicts),
        }

    if "bself" in arms:
        bundle["family_breakdown"] = family_breakdown(arms["bself"])
        bundle["confidence_histogram"] = confidence_histogram(arms["bself"])

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


def true_positive_showcase():
    """
    Real alerts where BOTH models' self-memory arm correctly escalated a
    genuine attack (verdict == true_positive). Filtered, not curated --
    every entry is a real row from the scored verdict files, joined on
    uid. Capped at 40 for payload size; the frontend can request more
    detail per-alert on demand if needed.
    """
    gemma = {r["uid"]: r for r in load_arm(MODELS["gemma"]["arms"]["bself"])}
    gptoss = {r["uid"]: r for r in load_arm(MODELS["gptoss"]["arms"]["bself"])}

    common_uids = set(gemma) & set(gptoss)
    out = []
    for uid in common_uids:
        g, p = gemma[uid], gptoss[uid]
        if g["verdict"] == "true_positive" and p["verdict"] == "true_positive":
            true_family = GT.get(uid, {}).get("attack")
            out.append({
                "uid": uid,
                "seq_gemma": g["seq"],
                "family_gemma": g["attack_category"],
                "family_gemma_correct": g["attack_category"] == true_family,
                "confidence_gemma": g["confidence"],
                "rationale_gemma": g["rationale_summary"],
                "family_gptoss": p["attack_category"],
                "family_gptoss_correct": p["attack_category"] == true_family,
                "confidence_gptoss": p["confidence"],
                "rationale_gptoss": p["rationale_summary"],
                "families_agree": g["attack_category"] == p["attack_category"],
                "true_family": true_family,
            })

    # Both-correct examples first -- genuinely the strongest cases to lead
    # with, without hiding that not every catch also names the family
    # right (shown honestly per-card via family_*_correct).
    out.sort(key=lambda r: (not (r["family_gemma_correct"] and r["family_gptoss_correct"]), r["seq_gemma"]))
    both_family_correct_count = sum(
        1 for r in out if r["family_gemma_correct"] and r["family_gptoss_correct"]
    )

    gemma_only_count = sum(1 for r in gemma.values() if r["verdict"] == "true_positive")
    gptoss_only_count = sum(1 for r in gptoss.values() if r["verdict"] == "true_positive")

    return {
        "both_models_count": len(out),
        "both_family_correct_count": both_family_correct_count,
        "gemma_count": gemma_only_count,
        "gptoss_count": gptoss_only_count,
        "examples": out[:40],
    }


# Qwen 3.8 27B has no raw per-verdict log in this repo (Section 4.6.2 of
# the report), so it can't be scored here the way Gemma and gpt-oss-20b
# are -- these are the already-published numbers from
# docs/status/qwen-results.md, included for the cross-model comparison
# only. Static-section only; Qwen is excluded from the Dynamic section
# and the true-positive showcase for the same reason.
QWEN_SUMMARY = {
    "label": "Qwen 3.8 27B",
    "source": "docs/status/qwen-results.md",
    "n_alerts": 250,
    "arms": {
        "A": {"recall": 0.020, "cat_accuracy": 0.020, "tp": 5, "fn": 245},
        "bself": {"recall": 0.000, "cat_accuracy": 0.000, "tp": 0, "fn": 250},
    },
    "mcnemar_p": 0.0625,
    "note": "Baseline recall is at the floor (2%); this result is about Qwen with this prompt, not about memory in general (docs/status/qwen-results.md).",
}


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

    cross_model["models"]["qwen"] = QWEN_SUMMARY
    with open(os.path.join(OUT_DIR, "cross_model.json"), "w", encoding="utf-8") as f:
        json.dump(cross_model, f, indent=2)
    print("wrote cross_model.json")

    with open(os.path.join(OUT_DIR, "true_positive_showcase.json"), "w", encoding="utf-8") as f:
        json.dump(true_positive_showcase(), f, indent=2)
    print("wrote true_positive_showcase.json")


if __name__ == "__main__":
    main()
