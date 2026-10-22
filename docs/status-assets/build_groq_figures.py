"""
Builds the 4 figures for docs/status/groq-gptoss20b-p1-results.md, the same
shape as build_p3_figures.py (docs/status-assets/) used for the
Gemma write-up. Read-only against the verdict files and ground truth; writes
PNGs beside itself only. Needs numpy and matplotlib only -- no embedding
model, no vector store, no network.

Usage (from the repo root, with src/ on PYTHONPATH):
    python docs/status-assets/build_groq_figures.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "src")
from memsoc.triage import score_verdicts as sv

ROOT = "artifacts/runs"
ARMS = {
    "A": f"{ROOT}/armA-gptoss20b-p1/triage_verdicts.jsonl",
    "self": f"{ROOT}/bself-gptoss20b-p1/triage_verdicts.jsonl",
    "oracle": f"{ROOT}/boracle-gptoss20b-p1/triage_verdicts.jsonl",
}
OUT = Path(__file__).parent
KEYS = ["A", "self", "oracle"]
NAMES = ["A (memory off)", "B-self", "B-oracle"]
COLORS = {"A": "#4e79a7", "self": "#f28e2b", "oracle": "#59a14f"}

gt = sv.read_ground_truth("artifacts/ground_truth.csv")


def load_per_alert(path):
    """Per-uid caught/named booleans, for the over-time and cold-start views
    that score_verdicts.py's own report() does not break out by alert."""

    rows = sv.read_verdicts(path)
    by_uid = {}

    for row in rows:
        g = gt.get(row["uid"])
        if g is None:
            continue
        want = sv.expected_category(g)
        by_uid[row["uid"]] = {
            "seq": row["seq"],
            "caught": row["verdict"] == "true_positive",
            "named": row["attack_category"] == want,
        }

    return by_uid


per_alert = {k: load_per_alert(path) for k, path in ARMS.items()}
scored = {k: sv.score(sv.read_verdicts(path), gt) for k, path in ARMS.items()}
n = scored["A"]["n"]

# ---- Figure 1: attacks missed by arm ----
missed = {k: scored[k]["fn"] for k in KEYS}
fig, ax = plt.subplots(figsize=(6, 3.2))
vals = [missed[k] for k in KEYS]
bars = ax.barh(NAMES, vals, color=[COLORS[k] for k in KEYS])
ax.set_xlabel(f"Attacks missed (of {n})")
ax.set_title("Attacks missed by arm -- Groq gpt-oss-20b")
for bar, v in zip(bars, vals):
    ax.text(v + 1, bar.get_y() + bar.get_height() / 2, str(v), va="center")
plt.tight_layout()
plt.savefig(OUT / "groq-01-attacks-missed.png", dpi=130)
plt.close()

# ---- Figure 2: missed attacks over time ----
ordered = {k: sorted(rows.items(), key=lambda kv: kv[1]["seq"]) for k, rows in per_alert.items()}
fig, ax = plt.subplots(figsize=(7, 3.5))
for k, name in zip(KEYS, NAMES):
    cum, c = [], 0
    for uid, r in ordered[k]:
        if not r["caught"]:
            c += 1
        cum.append(c)
    ax.plot(range(1, n + 1), cum, label=name, color=COLORS[k])
ax.set_xlabel("Alert number (stream order)")
ax.set_ylabel("Cumulative attacks missed")
ax.set_title("Missed attacks accumulating over the run")
ax.legend()
plt.tight_layout()
plt.savefig(OUT / "groq-02-misses-over-time.png", dpi=130)
plt.close()

# ---- Figure 3: catching vs naming ----
fig, ax = plt.subplots(figsize=(6, 3.2))
x = range(len(KEYS))
width = 0.35
ax.bar([i - width / 2 for i in x], [scored[k]["recall"] for k in KEYS], width,
       label="caught (recall)", color="#4e79a7")
ax.bar([i + width / 2 for i in x], [scored[k]["cat_accuracy"] for k in KEYS], width,
       label="named correctly", color="#e15759")
ax.set_xticks(list(x))
ax.set_xticklabels(NAMES)
ax.set_ylim(0, 1.05)
ax.set_title("Catching vs naming -- Groq gpt-oss-20b")
ax.legend()
plt.tight_layout()
plt.savefig(OUT / "groq-03-catching-vs-naming.png", dpi=130)
plt.close()

# ---- Figure 4: consistency on near-duplicate groups ----
# Same definition score_verdicts.py itself uses: same literal verdict/category
# value across the group, not "uniformly right or wrong".
gcount = scored["A"]["groups_multi"]
cv = {k: scored[k]["consistent_verdict"] / gcount for k in KEYS}
cc = {k: scored[k]["consistent_category"] / gcount for k in KEYS}

fig, ax = plt.subplots(figsize=(6, 3.2))
ax.bar([i - width / 2 for i in x], [cv[k] for k in KEYS], width,
       label="uniform verdict", color="#4e79a7")
ax.bar([i + width / 2 for i in x], [cc[k] for k in KEYS], width,
       label="uniform category", color="#e15759")
ax.set_xticks(list(x))
ax.set_xticklabels(NAMES)
ax.set_ylim(0, 1.05)
ax.set_title(f"Consistency on {gcount} near-duplicate groups -- Groq gpt-oss-20b")
ax.legend()
plt.tight_layout()
plt.savefig(OUT / "groq-04-consistency.png", dpi=130)
plt.close()

print(f"Wrote 4 figures to {OUT}")
