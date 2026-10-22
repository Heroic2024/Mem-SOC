"""Render the Gemma p3 results figures without the notebook.

The notebook cannot be executed to completion (BL-132): its cell 8 embeds
all 1135 alerts and dies natively. None of the *results* figures need an
embedding -- they need the three verdict files and the frozen scorer --
so this renders them directly. Metric definitions are not re-derived
here: every number comes from memsoc.triage.score_verdicts, unchanged.

Colours are the dataviz reference palette's first three categorical
slots, one per arm, held identical across every figure so a colour means
an arm and nothing else. The aqua slot carries a contrast warning
against the light surface, so every mark is directly labelled.
"""

import json
import math
import os
import sys

# The summary at the end prints block characters, which a cp1252 Windows
# console cannot encode; without this the script dies after writing every
# figure and reports failure for a successful run.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # docs/status-assets -> repo root

sys.path.insert(0, os.path.join(ROOT, "src"))

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from memsoc import paths
from memsoc.triage import score_verdicts

RUN_TAG = "gemma4-26b-p3"
ARMS = {
    "A (memory off)": f"armA-{RUN_TAG}",
    "B-self": f"bself-{RUN_TAG}",
    "B-oracle": f"boracle-{RUN_TAG}",
}

# dataviz reference palette -- categorical slots 1/2/3, light mode.
COLOUR = {
    "A (memory off)": "#2a78d6",
    "B-self": "#eb6834",
    "B-oracle": "#1baf7a",
}

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# These figures are committed documentation assets, not runtime output, so
# they sit beside this script -- the same arrangement as docs/design-assets/.
# artifacts/figures/ is gitignored, which would leave the write-up's images
# broken for anyone who cloned the repo.
OUT = HERE

plt.rcParams.update({
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_2,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlesize": 12,
    "font.size": 9,
})


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    print("saved", path)


def rounded_bar(ax, x, y, w, h, colour, radius=0.035, horizontal=False):
    """A plain thin bar.

    FancyBboxPatch rounding was tried and abandoned: its corner radius is
    one number applied to two axes with different data units, which blew
    the ends out into spikes. A square end that is honest about the value
    beats a rounded one that is not.
    """

    ax.add_patch(Rectangle((x, y), w, h, linewidth=0, facecolor=colour))


# ---------------------------------------------------------------- data

gt = score_verdicts.read_ground_truth(paths.GROUND_TRUTH)

runs = {}
for arm, run_id in ARMS.items():
    path = os.path.join(paths.run_dir(run_id), "triage_verdicts.jsonl")
    rows = {r["uid"]: r for r in score_verdicts.read_verdicts(path)}
    runs[arm] = sorted(rows.values(), key=lambda r: r["seq"])

paired = set.intersection(*[{r["uid"] for r in rs} for rs in runs.values()])
order = sorted(paired, key=lambda u: {r["uid"]: r["seq"] for r in runs["A (memory off)"]}[u])
by_arm = {arm: {r["uid"]: r for r in rs} for arm, rs in runs.items()}

print(f"{len(order)} alerts triaged by all three arms")

S = {}
ESC = {}
FAM = {}
for arm in ARMS:
    rows = [by_arm[arm][u] for u in order]
    S[arm] = score_verdicts.score(rows, gt)
    ESC[arm] = [r["verdict"] == "true_positive" for r in rows]
    FAM[arm] = [r["attack_category"] == score_verdicts.expected_category(gt[r["uid"]])
                for r in rows]

N = len(order)
DET = S["A (memory off)"]["det_accuracy"]

for arm in ARMS:
    s = S[arm]
    print(f"  {arm:<16} tp {s['tp']:>3} fn {s['fn']:>3}  recall {s['recall']:.3f}  "
          f"cat {s['cat_accuracy']:.3f}  uniform {s['consistent_verdict']}/{s['groups_multi']} "
          f"verdict, {s['consistent_category']}/{s['groups_multi']} family  "
          f"latency {s['mean_latency_ms'] / 1000:.1f}s")
print(f"  detector family accuracy on these alerts: {DET:.3f}")


def mcnemar(a_ok, b_ok):
    """Exact two-sided McNemar test, as the notebook defines it."""

    b = sum(x and not y for x, y in zip(a_ok, b_ok))
    c = sum(y and not x for x, y in zip(a_ok, b_ok))
    m = b + c
    if m == 0:
        return b, c, 1.0
    tail = sum(math.comb(m, k) for k in range(min(b, c) + 1)) / 2 ** m
    return b, c, min(1.0, 2 * tail)


print("\nMcNemar vs Arm A:")
STATS = {}
for arm in ("B-self", "B-oracle"):
    for metric, got in (("escalated", ESC), ("family", FAM)):
        b, c, p = mcnemar(got["A (memory off)"], got[arm])
        STATS[(arm, metric)] = (b, c, p)
        print(f"  {arm:<10} {metric:<10} A-right/B-wrong {b:>3}  A-wrong/B-right {c:>3}  p={p:.2e}")


# ------------------------------------------- figure 1: attacks missed

fig, ax = plt.subplots(figsize=(6.6, 2.5))

arms = list(ARMS)
for i, arm in enumerate(arms):
    miss = S[arm]["fn"]
    y = len(arms) - 1 - i
    rounded_bar(ax, 0, y - 0.3, miss, 0.6, COLOUR[arm], radius=0.06, horizontal=True)
    ax.text(miss + 1.2, y, f"{miss}", va="center", ha="left",
            fontsize=12, fontweight="bold", color=INK)
    ax.text(miss + 6.5, y, f"of {N} attacks", va="center", ha="left",
            fontsize=8.5, color=MUTED)

ax.set_yticks(range(len(arms)))
ax.set_yticklabels(arms[::-1], fontsize=9.5, color=INK_2)
ax.set_xlim(0, 56)
ax.set_ylim(-0.6, len(arms) - 0.4)
ax.set_xlabel("real attacks wrongly dismissed as harmless", color=INK_2)
ax.xaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
ax.spines["left"].set_color(AXIS)
ax.set_title("Memory cut the attacks Gemma missed", loc="left",
             fontweight="bold", color=INK, pad=10)
save(fig, "p3-01-attacks-missed.png")


# --------------------------------- figure 2: misses accumulate (lines)

fig, ax = plt.subplots(figsize=(6.6, 3.4))

x = np.arange(1, N + 1)
for arm in arms:
    missed = np.cumsum([0 if ok else 1 for ok in ESC[arm]])
    ax.plot(x, missed, linewidth=2, color=COLOUR[arm], solid_capstyle="round")
    ax.annotate(f"{arm}  {missed[-1]}",
                xy=(N, missed[-1]), xytext=(6, 0), textcoords="offset points",
                va="center", ha="left", fontsize=8.5,
                color=INK_2, fontweight="bold")

ax.set_xlim(1, N)
ax.set_ylim(0, 48)
ax.set_xlabel("alerts seen, in the order they arrived", color=INK_2)
ax.set_ylabel("attacks missed so far", color=INK_2)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
ax.set_title("The gap opens early and never closes", loc="left",
             fontweight="bold", color=INK, pad=10)
fig.subplots_adjust(right=0.78)
save(fig, "p3-02-misses-over-time.png")


# ------------------------- figure 3: catching vs naming (grouped bars)

fig, ax = plt.subplots(figsize=(6.6, 3.4))

groups = [
    ("Caught the attack\n(escalated a real attack)", "escalated"),
    ("Named the attack type\n(correct family)", "family"),
]
width = 0.26
for gi, (label, metric) in enumerate(groups):
    for ai, arm in enumerate(arms):
        rate = (S[arm]["recall"] if metric == "escalated"
                else S[arm]["cat_accuracy"])
        xpos = gi + (ai - 1) * (width + 0.02)
        rounded_bar(ax, xpos - width / 2, 0, width, rate * 100, COLOUR[arm],
                    radius=0.05)
        ax.text(xpos, rate * 100 + 2.5, f"{rate * 100:.0f}%", ha="center",
                va="bottom", fontsize=9, fontweight="bold", color=INK)

# The detector only names families; it issues no escalate/dismiss verdict.
# So the reference line stops at the group it is a reference for.
ax.plot([0.56, 1.5], [DET * 100] * 2, color=MUTED, linewidth=1.2,
        linestyle=(0, (4, 3)), zorder=1)
ax.text(1.5, DET * 100 + 1.5, f"detector alone, {DET * 100:.0f}%",
        ha="right", va="bottom", fontsize=8, color=MUTED, style="italic")

ax.set_xticks(range(len(groups)))
ax.set_xticklabels([g[0] for g in groups], fontsize=9, color=INK_2)
ax.set_xlim(-0.55, 1.55)
ax.set_ylim(0, 108)
ax.set_ylabel("percent of the 165 alerts", color=INK_2)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)

handles = [plt.Rectangle((0, 0), 1, 1, facecolor=COLOUR[a], linewidth=0) for a in arms]
ax.legend(handles, arms, frameon=False, fontsize=8.5, ncol=3,
          loc="upper center", bbox_to_anchor=(0.5, 1.14), labelcolor=INK_2)
ax.set_title("Memory helped the verdict and hurt the label", loc="left",
             fontweight="bold", color=INK, pad=26)
save(fig, "p3-03-catching-vs-naming.png")


# ------------------------------ figure 4: consistency on near-duplicates

fig, ax = plt.subplots(figsize=(6.6, 3.2))

G = S["A (memory off)"]["groups_multi"]
groups = [
    ("Gave the same verdict", "consistent_verdict"),
    ("Gave the same attack type", "consistent_category"),
]
for gi, (label, key) in enumerate(groups):
    for ai, arm in enumerate(arms):
        k = S[arm][key]
        xpos = gi + (ai - 1) * (width + 0.02)
        rounded_bar(ax, xpos - width / 2, 0, width, k, COLOUR[arm], radius=0.05)
        ax.text(xpos, k + 0.35, f"{k}", ha="center", va="bottom",
                fontsize=9, fontweight="bold", color=INK)

ax.set_xticks(range(len(groups)))
ax.set_xticklabels([g[0] for g in groups], fontsize=9, color=INK_2)
ax.set_xlim(-0.55, 1.55)
ax.set_ylim(0, G + 3)
ax.set_ylabel(f"groups of near-identical alerts (of {G})", color=INK_2)
ax.set_yticks(range(0, G + 2, 2))          # whole groups; half a group is not a thing
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
ax.legend(handles, arms, frameon=False, fontsize=8.5, ncol=3,
          loc="upper center", bbox_to_anchor=(0.5, 1.14), labelcolor=INK_2)
ax.set_title("Self-memory made every repeat answer agree", loc="left",
             fontweight="bold", color=INK, pad=26)
save(fig, "p3-04-consistency.png")


# -------------------------------------------------- text bars for the doc

print("\n--- unicode bars for the markdown ---")


def bar(value, scale, width=22):
    filled = int(round(value / scale * width))
    return "\u2588" * max(filled, 1 if value > 0 else 0)


for arm in arms:
    print(f"missed {arm:<16} {bar(S[arm]['fn'], 50):<24} {S[arm]['fn']}")
print()
for arm in arms:
    print(f"recall {arm:<16} {bar(S[arm]['recall'] * 100, 100):<24} {S[arm]['recall']:.1%}")
print()
for arm in arms:
    print(f"family {arm:<16} {bar(S[arm]['cat_accuracy'] * 100, 100):<24} {S[arm]['cat_accuracy']:.1%}")
print(f"family {'detector':<16} {bar(DET * 100, 100):<24} {DET:.1%}")
print()
for arm in arms:
    ms = S[arm]["mean_latency_ms"] / 1000
    print(f"secs   {arm:<16} {bar(ms, 45):<24} {ms:.0f}s")

print("\njson for the doc:")
print(json.dumps({arm: {k: S[arm][k] for k in
                        ("tp", "fn", "recall", "precision", "f1", "cat_accuracy",
                         "agreement", "groups_multi", "consistent_verdict",
                         "consistent_category", "mean_latency_ms", "inconclusive")}
                  for arm in arms}, indent=1))
print("detector:", DET)
print("mcnemar:", {f"{a}/{m}": v for (a, m), v in STATS.items()})
