"""
Builds the cross-model comparison figures for
docs/status/three-model-comparison.md.

Groq's numbers are computed live from its real verdict files (the only
raw run data present in this repo -- Gemma's and Qwen's were never
committed, by design; artifacts/ is gitignored). Gemma's and Qwen's
numbers below are copied from their own published write-ups
(docs/status/gemma-p3-results.md, docs/status/qwen-results.md) and are
NOT recomputed here -- there is no raw data to recompute them from.
Each hardcoded figure below cites the exact line it came from.

Usage (from the repo root, with src/ on PYTHONPATH):
    python docs/status-assets/build_comparison_figures.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "src")
from memsoc.triage import score_verdicts as sv

OUT = Path(__file__).parent

# ---- Groq: computed live from real data ----
gt = sv.read_ground_truth("artifacts/ground_truth.csv")
ROOT = "artifacts/runs"
groq_verdicts = {
    "A": sv.read_verdicts(f"{ROOT}/armA-gptoss20b-p1/triage_verdicts.jsonl"),
    "self": sv.read_verdicts(f"{ROOT}/bself-gptoss20b-p1/triage_verdicts.jsonl"),
    "oracle": sv.read_verdicts(f"{ROOT}/boracle-gptoss20b-p1/triage_verdicts.jsonl"),
}
groq_scores = {k: sv.score(v, gt) for k, v in groq_verdicts.items()}

# ---- Gemma: from docs/status/gemma-p3-results.md section 8 ----
gemma = {
    "A": {"recall": 0.745, "cat_accuracy": 0.545},
    "self": {"recall": 0.867, "cat_accuracy": 0.236},
    "oracle": {"recall": 0.988, "cat_accuracy": 0.691},
}

# ---- Qwen: from docs/status/qwen-results.md section 7 (no oracle arm) ----
qwen = {
    "A": {"recall": 0.020, "cat_accuracy": 0.020},
    "self": {"recall": 0.000, "cat_accuracy": 0.000},
    "oracle": None,
}

MODELS = ["Gemma 4 26B", "Groq gpt-oss-20b", "Qwen 3.8 27B"]
ARMS = ["A", "self", "oracle"]
ARM_LABELS = ["A (no memory)", "B-self", "B-oracle"]
COLORS = {"Gemma 4 26B": "#59a14f", "Groq gpt-oss-20b": "#4e79a7", "Qwen 3.8 27B": "#e15759"}


def value(model, arm, metric):
    if model == "Gemma 4 26B":
        return gemma[arm][metric]
    if model == "Qwen 3.8 27B":
        return qwen[arm][metric] if qwen[arm] else None
    return groq_scores[arm][metric]


def grouped_bar(metric, title, filename):
    fig, ax = plt.subplots(figsize=(8, 4))
    x = range(len(ARMS))
    width = 0.25

    for i, model in enumerate(MODELS):
        vals = [value(model, arm, metric) for arm in ARMS]
        positions = [xi + (i - 1) * width for xi in x]
        # Missing (Qwen oracle) plots as 0 height with a hatch, not silently omitted.
        heights = [v if v is not None else 0 for v in vals]
        bars = ax.bar(positions, heights, width, label=model, color=COLORS[model])
        for pos, v, bar in zip(positions, vals, bars):
            if v is None:
                bar.set_hatch("//")
                bar.set_alpha(0.3)
                ax.text(pos, 0.02, "not run", rotation=90, fontsize=7, va="bottom", ha="center")

    ax.set_xticks(list(x))
    ax.set_xticklabels(ARM_LABELS)
    ax.set_ylim(0, 1.05)
    ax.set_title(title)
    ax.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(OUT / filename, dpi=130)
    plt.close()


grouped_bar("recall", "Recall by arm, across all three models", "compare-01-recall.png")
grouped_bar("cat_accuracy", "Category accuracy by arm, across all three models", "compare-02-cat-accuracy.png")

# ---- Figure 3: the self-memory effect (self minus A), all three models ----
fig, ax = plt.subplots(figsize=(7, 4))
recall_deltas = []
cat_deltas = []
for model in MODELS:
    a_r = value(model, "A", "recall")
    s_r = value(model, "self", "recall")
    a_c = value(model, "A", "cat_accuracy")
    s_c = value(model, "self", "cat_accuracy")
    recall_deltas.append(s_r - a_r)
    cat_deltas.append(s_c - a_c)

x = range(len(MODELS))
width = 0.35
bars1 = ax.bar([i - width / 2 for i in x], recall_deltas, width, label="recall (self - A)", color="#4e79a7")
bars2 = ax.bar([i + width / 2 for i in x], cat_deltas, width, label="category accuracy (self - A)", color="#e15759")
ax.axhline(0, color="black", linewidth=0.8)
ax.set_xticks(list(x))
ax.set_xticklabels(MODELS)
ax.set_title("Self-memory's effect, relative to no memory -- all three models")
ax.set_ylabel("Change vs Arm A (points)")
ax.legend(fontsize=8)
for bars in (bars1, bars2):
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + (0.01 if h >= 0 else -0.03),
                 f"{h:+.1%}", ha="center", fontsize=8)
plt.tight_layout()
plt.savefig(OUT / "compare-03-self-memory-effect.png", dpi=130)
plt.close()

print("Wrote 3 comparison figures to", OUT)
print("Groq live scores:", {k: {"recall": v["recall"], "cat_accuracy": v["cat_accuracy"]} for k, v in groq_scores.items()})
