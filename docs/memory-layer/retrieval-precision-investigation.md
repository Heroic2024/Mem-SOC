# Retrieval Precision Investigation — Findings, Issues, and Recommendations

> Scope: a Phase 0 diagnostic investigation into whether alert-only text
> embedding retrieves usefully, run before building the production
> `CaseRenderer` / `Retriever` modules. Re-runs and extends [`BL-014`](../PRODUCT_BACKLOG.md),
> on the clean held-out stream instead of the contaminated one it was
> originally measured on.
>
> **Date:** 2026-10-11/12. **Owner:** Person 1 (memory layer).
> **Status: investigation complete; findings below feed the C1/C2/C8 decisions
> and should be logged to `PRODUCT_BACKLOG.md` and `decisions.md` per this
> project's own rule that an unwritten finding is not a finding.**

---

## 1. Why this investigation happened

Before writing the production memory-layer code, a cheap, zero-cost check was
run first: does similarity search over rendered alert text actually find
genuinely similar past attacks? `BL-014`'s original measurement — on
contaminated data — found retrieval *worse than random* on exactly the
alerts the detector got wrong. Before building an entire module on top of
that assumption, it needed re-measuring on real, clean data.

---

## 2. Environment and infrastructure findings

None of this existed on the machine this work was done on. Recording it
here because the next person to set up this machine, or a similar one, will
hit the same gaps `BL-107` already predicted.

| Finding | Detail |
|---|---|
| **No `artifacts/`, no `data/`, no memory venv existed on this machine** | The repository had never been run here. `BL-107`'s concern — that the memory venv's location (`C:/Users/Aryan Mhatre/.venvs/memsoc-memory`) is recorded only in a comment and is machine-specific — is now confirmed as a real, not hypothetical, onboarding problem. |
| **The dataset existed, but not where the repo expects it** | Found at `Downloads/archive (1)/NF-UNSW-NB15-v3.csv`, not `data/`. `paths.py`'s `MEMSOC_DATASET_CSV` override handled this cleanly — worth documenting as the expected path for a fresh machine rather than assuming `data/` is always pre-populated. |
| **Two separate venvs were needed, by design** | One for `requirements/memory.txt` (chromadb, sentence-transformers, torch), one for `requirements/detection.txt` (lightgbm, scikit-learn, pandas) — confirms the separation `CLAUDE.md` and `requirements/memory.txt`'s own header describe is correct and necessary, not excessive caution. |
| **All four invariants in `requirements/memory.txt` verified independently** | Embedding determinism, real cosine distance space (asserted on actual distances, not the config string), store persistence across reopen, and silent truncation at 256 tokens — all confirmed on this machine, not assumed from the prior sandbox report. Script: `scratchpad/memory_invariant_check.py`. |
| **`BL-013`'s silent-truncation failure mode reproduced exactly** | A 1,602-token input produced no exception — only an unlogged `transformers`-library `stderr` warning. Confirms the renderer's length check must be an explicit manual `len(tokenizer.encode(text))` comparison; it cannot rely on `encode()` raising. |
| **The held-out split recovery (`BL-025`/`BL-028`) reproduces exactly on a second machine** | Every per-class F1, accuracy, and the order-sensitive 72/100 check matched the published fingerprint. This is strong independent confirmation the recovery is correct, not a one-machine artifact. |
| **Resolved dependency versions drift slightly from the original sandbox's, as expected** | `torch 2.14.1` / `transformers 5.19.0` / `numpy 2.5.4` here vs. `2.14.0+cpu` / `5.17.0` / `2.5.3` previously — expected and acceptable, since only `chromadb` and `sentence-transformers` are actually pinned; the file's own comment explains why `torch` is deliberately left unpinned. Recorded at `artifacts/memory-env-freeze.txt`. |

---

## 3. Retrieval precision findings — the core result

**Method:** 95 real attacks captured from the clean, held-out stream
(`stream_version 2`). For each attack, rendered alert-only text, embedded
with `all-MiniLM-L6-v2`, found its nearest *other* attack by cosine
similarity, and checked whether that neighbor shares its true attack
family — both overall and restricted to the 24 attacks the detector itself
got wrong (the population memory exists to help with). Script:
`scratchpad/memory_retrieval_test.py`.

| Variant | Overall match | Hard-case match (n=24) | Note |
|---|---|---|---|
| Alert + detector's label | 58.9% | 12.5% (3/24) | Matches `C1`'s "worse" condition — not the recommended one |
| True alert-only, raw numbers | 45.3% | 16.7% (4/24) | The actually-recommended `C1` condition |
| **Alert-only + SHAP feature names, raw numbers** | **52.6%** | **20.8% (5/24)** | **Best found** |
| Alert-only + SHAP feature names, bucketed magnitude words | 51.6% | 16.7% (4/24) | Regression — see §4 |

**Supporting evidence, consistent across every variant:**
- Similarity scores for *correct* nearest-neighbor matches and *incorrect*
  ones are consistently close together (e.g., median 0.979 vs. 0.970 in the
  best-performing variant) — no threshold value would separate good
  retrievals from bad ones.
- Worked examples show many "nearest neighbor" pairs sharing nothing more
  specific than destination port 80 / TCP — a combination common enough
  across unrelated attack families that it carries little discriminating
  signal in this dataset.

**Headline finding: `BL-014`'s result reproduces on clean data.** The
contamination bug (`BL-025`) was not the cause of poor retrieval. Hard-case
match rate stayed in a narrow 12–21% band across four independently
reasoned variants, never approaching the detector's own accuracy (74.7% on
the same batch).

---

## 4. Issues found during the investigation

### 4.1 — A real inconsistency between `C1`'s evidence and the actual template

`decisions.md` C1's cited evidence — *"adding only the detector's one-line
answer... raised the overall match rate from 64% to 77%, but dropped it
from 21% to 4%"* — compares a baseline **without** the detector's label
line against one **with** it. But [`02-case-schema.md`](./02-case-schema.md)'s
own "alert-only" template already includes `Detector: {detector_label}
score {detector_score:.2f}` as line 3.

**Consequence:** the schema's own definition of "alert-only" does not
match the condition the recommendation's evidence actually measured as
good. This investigation's first test run made the same mistake — copying
the template faithfully, and so unintentionally testing the *worse*
condition first. Re-running without that line confirmed the evidence's
direction (hard-case match improved 12.5% → 16.7%), but the gain was much
smaller than the originally reported 21%.

**Needs fixing:** either `02-case-schema.md`'s template should drop the
detector-label line to match what the evidence recommends, or the C1
evidence citation needs updating to reflect what the current template
actually renders. Left as-is, anyone reading the schema doc and
implementing from it will reproduce the worse condition without realizing
it.

### 4.2 — Bucketing numeric magnitudes into words did not help, and slightly regressed

Hypothesis tested: since sentence-embedding models have no real notion of
numeric magnitude ([R7](./06-risks-and-limitations.md#r7--numeric-features-in-a-text-embedding-space)),
converting raw numbers (`"Rate: 412 pkt/s"`) into words a language model
can actually reason about (`"Rate: very high"`) should help.

**Result:** hard-case match rate went 20.8% → 16.7% — a regression, not an
improvement.

**Likely cause:** bucket thresholds were computed from the whole traffic
population (99%+ benign), so "high" and "very high" are calibrated to
normal traffic. Attacks, being abnormal by nature, likely cluster into the
same one or two extreme buckets regardless of which specific attack family
they belong to — collapsing distinctions the raw numbers had still weakly
preserved. Untested but plausible alternative: compute bucket thresholds
from attack traffic only (still no label/ground-truth leakage, since this
doesn't require knowing *which* attack family, only that a flow was
flagged) — not tried here due to time, worth a follow-up if the team wants
to continue down this path.

### 4.3 — Embedding the LLM's verdict was considered and ruled out, not just deprioritized

Raised as an option (include the LLM's conclusion in the embedded text, not
just the detector's). **Not tested, because it fails structurally, not just
on accuracy:** a new, not-yet-triaged alert has no verdict to embed at query
time, so the query and document texts would be built from fundamentally
different shapes — violating the symmetry requirement
[`02-case-schema.md`](./02-case-schema.md#the-symmetry-requirement) and
[`01-architecture.md`](./01-architecture.md) both describe as load-bearing.
This is a harder failure than the detector-label problem (§4.1), which at
least stays symmetric (the detector classifies every alert, including new
ones, before retrieval happens).

---

## 5. Recommendations

1. **Build the Phase 2 default renderer as: alert-only text + top-3 SHAP
   feature names, raw (non-bucketed) numbers.** This is the best-measured
   configuration (20.8% hard-case match) and is legitimate — no leakage,
   symmetric between read and write paths.
2. **Do not bucket/discretize numeric fields** in the current form. If
   revisited, compute thresholds from attack-only traffic rather than the
   whole population first, as a distinct follow-up experiment.
3. **Do not embed the LLM's verdict or rationale**, under any configuration
   — this is not a tuning question, it structurally breaks query/document
   symmetry.
4. **Fix the `C1` / `02-case-schema.md` inconsistency** (§4.1) before the
   schema is treated as locked — whichever direction is chosen, the
   evidence and the template need to agree.
5. **Raise the numeric-distance hybrid retrieval question with the team as
   an explicit, named decision.** [R7](./06-risks-and-limitations.md#r7--numeric-features-in-a-text-embedding-space)
   already identifies this as the change most likely to meaningfully
   improve retrieval, and already flags it as "a second variable, out of
   scope" for the current design — meaning it's a deliberate choice
   already made, not an oversight, but one worth re-confirming given how
   consistently weak every text-only variant performed.
6. **Consider the manual relevance audit** ([`04-read-path.md`](./04-read-path.md#retrieval-quality-audit))
   before concluding further — it answers a different question than this
   investigation did (whether retrieved cases are *relevant*, not just
   whether their category label matches), and the project's own docs
   already specify the protocol for it.
7. **Treat a null or negative result on Arm B as a live, well-supported
   possibility**, not a remote one. This investigation's findings are
   consistent with, and strengthen, `BL-014`'s original warning. The paper
   should be structured to remain publishable under that outcome, per the
   guidance already in `work-split.md`.
8. **Document the dataset/venv path issue (§2) in the setup guide**, since
   this machine hit every gap `BL-107` predicted, confirming it's a real
   onboarding risk rather than a hypothetical one.

---

## 6. What this investigation does not resolve

- Whether a retrieval-tuned embedding model (e.g., `bge-small-en-v1.5`)
  performs meaningfully better — not tested; flagged as a cheap follow-up
  if the team wants more evidence before committing to the hybrid-retrieval
  decision in recommendation 5.
- The full-scale result on all 215 held-out attacks rather than this
  95-attack batch — the batch size here is smaller than `BL-014`'s original
  211, so these figures should be read as directionally consistent, not as
  a final, precise replacement for a full-population measurement.
- Whether the attack-family taxonomy itself is the right unit to measure
  "relevance" against (see recommendation 6).

---

## Where the rest of the detail lives

| For | Read |
|---|---|
| The diagnostic scripts themselves | `scratchpad/memory_invariant_check.py`, `scratchpad/memory_retrieval_test.py` — **never committed and no longer available (BL-115).** Superseded on 2026-10-13 by [`notebooks/retrieval-quality.ipynb`](../../notebooks/retrieval-quality.ipynb), which re-measures this with the production template over all 215 alerts, and by `tests/test_memory.py`, which covers the invariants. |
| The original contaminated-data measurement this extends | [`PRODUCT_BACKLOG.md`](../PRODUCT_BACKLOG.md) `BL-014` |
| The case schema and the C1 inconsistency this found | [`02-case-schema.md`](./02-case-schema.md) |
| The numeric-embedding risk this confirms | [`06-risks-and-limitations.md`](./06-risks-and-limitations.md) R7 |
| The manual audit protocol (recommendation 6) | [`04-read-path.md`](./04-read-path.md#retrieval-quality-audit) |
| Project-wide decisions this should be logged against | [`decisions.md`](../decisions.md) C1, C2, C8 |
