# Protocol v4 (supplementary experiments): time estimate

> **Status:** plan and estimate only. Nothing below has been implemented or run yet.
> **Date:** 2026-10-29
> **Scope:** the approved extension to the Gemma 4 26B three-arm result ([`gemma-p3-results.md`](./gemma-p3-results.md)). The frozen p3 results stay untouched and are the main experiment. Everything here is **supplementary**, under a new code tag.

---

## Summary

| | Estimate |
|---|---|
| **Hands-on work** (build, check, score, write up) | **about 22–33 hours** |
| **Unattended Gemma runs** | **about 700 calls, 5–8.5 hours** (plus about 1 hour if the optional random benign set is run) |
| **Calendar time** | **3–4 working days** |

**Where the run times come from:** the p3 Gemma run took 20–40 s per alert, and 495 calls took 4–7 hours ([`testing-protocol-v3.md`](./testing-protocol-v3.md) §3). Gemma's daily limit is 14,400 requests (`src/memsoc/triage/config.py`, `DAILY_REQUEST_LIMITS`), so quota does not slow anything down. Only per-call speed matters.

---

## What was approved

1. **Shuffled-label memory.** The retrieved cases stay exactly the same. For each query, each retrieved case's label is replaced with a true label sampled from all cases stored so far. The sampling seed is derived from the alert ID, so the class mix of the labels is unchanged. It starts from the B-oracle (true-label) write path, so the only thing destroyed is label content. Every replacement is logged for auditing.
2. **Label-free memory.** B-self with the attack family removed. Stored cases keep the alert text, the model's own escalate/dismiss verdict and its confidence. The precedent block shows only those. The response schema and the rest of the prompt are unchanged, so family accuracy can still be scored.
3. **Hard-benign test.** The 100 held-out benign flows with the highest detector scores, sent directly to the LLM. The detector and its thresholds are unchanged, and the multiclass family guess is shown as for any alert. Rows come only from data the detector never trained on, and near-duplicates are removed. The selection rule (ranking, seed, de-duplication method) is fixed and the final list is hashed before any run. Optional: 50 random benign flows as a second set.
4. **Attack-primed mixed stream.** The 100 benign flows run after the existing 165 attacks. B-self starts from a copy of its memory at the end of the p3 run and keeps writing back. The copy's case count is checked and its hash recorded. Arm A runs on the same 100 flows so the comparison is paired. The main metric is the false-escalation rate on benign flows.
5. **Reversed order.** The exact reverse of the 165-alert sequence, B-self only. Arm A judges each alert independently of order, so its existing results are reused.
6. **Nearest-neighbour baseline, recomputed.** A three-neighbour vote using the text-embedding retrieval the LLM runs actually used, with earlier alerts only and true labels, on the same 165 alerts. The numeric-feature variant may be shown as a separate row. The 1,135-alert figure is not compared with the 165-alert results.

---

## Per-task breakdown

| # | Task | Build / write | Gemma run (unattended) |
|---|---|---|---|
| 0 | **Protocol v4 setup:** new code tag, separate run-id prefix so the frozen v3 results stay untouched, startup checks, hash recording | 2–3 h | — |
| 0b | **Pre-registration note:** definitions, hypotheses with what result would support or contradict each, metrics, and a commitment to report all results. Committed before the first run so it is time-stamped | 1–1.5 h | — |
| 1 | **Shuffled-label memory:** new memory condition on the B-oracle write path, seeded label replacement, replacement log, check that the class mix is unchanged | 3–4 h | 165 calls ≈ 1–1.8 h |
| 2 | **Label-free memory:** B-self with the family removed from stored cases and the precedent block; schema unchanged | 2–3 h | 165 calls ≈ 1–1.8 h |
| 3 | **Hard-benign selection:** recover held-out rows, score with the frozen detector, take the top 100, remove near-duplicates, build them into alerts (SHAP plus multiclass guess), hash the list. Optional random 50 | 4–8 h (**main risk**) | — |
| 4 | **Attack-primed mixed stream:** copy the B-self store, verify its case count, hash it; run B-self (with write-back) and Arm A on the same 100 flows | 2–3 h | 200 calls ≈ 1.2–2.2 h (+100 calls ≈ 0.6–1.1 h for the random set) |
| 5 | **Reversed order:** exact reverse of the 165 alerts, B-self only, fresh store | 1 h | 165 calls ≈ 1–1.8 h |
| 6 | **Nearest-neighbour baseline recomputed** on the 165 alerts with the retrieval the runs actually used | 1–2 h | — (no LLM calls) |
| 7 | **Checks before the overnight runs:** contract tests, a one-alert dry run per new condition, confirming Arm A never writes to memory | 1.5–2 h | ~10 calls |
| 8 | **Scoring and supplementary write-up:** false-escalation rate, family accuracy per arm, paired tests, "hard-benign" and "attack-primed" framing | 4–6 h | — |
| 9 | **Backlog rows and docs index** (required by `CLAUDE.md`) | 1 h | — |
| | **Total** | **≈ 22–33 h** | **≈ 700 calls ≈ 5–8.5 h** |

---

## Proposed schedule

| When | Work |
|---|---|
| **Day 1** | Tasks 0, 0b, 1, 2 and 6, then the dry runs. **Overnight:** label-free and shuffled-label runs (330 calls, about 2–3.5 h) |
| **Day 2** | Task 3 (benign selection); commit the list's hash; build task 4. **Overnight:** benign runs plus the reversed order (365 calls, about 2.5–4 h) |
| **Day 3 (and possibly day 4)** | Scoring, supplementary write-up, backlog and docs |

**If time runs short** (as agreed): drop the reversed order first, then the random benign set. That saves about 2–3 hours in total. Keep everything else.

---

## Risks that could stretch the estimate

1. **The dataset and held-out index are not yet available locally.** `data/` is empty and `artifacts/heldout_rows.npy` has not been generated. Selecting held-out benign rows needs the full NF-v3 dataset (about 2.35M rows) and a run of `python -m memsoc.detection.training.heldout_split`. That script writes no index unless it reproduces the detector's published fingerprint. If the fingerprint does not reproduce, task 3 is **blocked** and needs a team decision, not just more hours.
2. **Label-free memory may touch the shared prompt.** If the precedent block is rendered in `src/memsoc/triage/triage_prompt.py` and not inside the memory module, removing the family there comes close to the protected base prompt template. This will be checked first and raised with the team before any edit.
3. **The p3 B-self memory store must be available** with the expected 165 cases, or the mixed-stream test (task 4) cannot start from it. Not checked yet.

---

## Integrity rules that apply throughout

- The frozen p3 results are never modified. All new runs are labelled supplementary, protocol v4.
- The detector, its thresholds, the embedding model, the base prompt and the seeds stay unchanged.
- The pre-registration note and the benign-list hash are committed **before** the first new run.
- All results are reported, favourable or not.
