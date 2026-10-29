# New Experiments Asked for by the Paper Review

> **What this is:** the experiments that the 2026-10-28 review of the research paper says are needed, turned
> into a run plan. Writing-only fixes from the same review (claims, p-value wording, figure order, references,
> length, template) are **not** here — they need no new runs.
> **Source:** `documentation/research-paper/review_for_paper.md` (gitignored), points 1–8.
> **Status:** plan only. **Nothing here has been run.** Every experiment has a backlog row (§9).
> **Written:** 2026-10-28.

---

## 1. The short version

The review's main objection is that the experiment, as run, **cannot show that memory helps triage**:

- Every alert the LLM saw was a real attack, so recall only measures how willing the model is to say "attack".
- Each arm ran once, in one fixed alert order, and memory makes the result depend on that order.
- There are no controls showing *why* memory helps or hurts, and nothing shows the LLM adds anything over the detector.
- Retrieval often fetches the wrong kind of past case, so "memory of similar cases" is weaker than the paper claims.

The experiments below answer those objections. In order of importance:

| # | Experiment | Answers review point | LLM calls? | Size |
|---|---|---|---|---|
| E1 | Add harmless (benign) traffic to what the LLM triages | 1 | yes | large |
| E2 | Re-check the detector for near-duplicate training leakage | 1 | **no** | small |
| E3 | Run each arm several times, in different alert orders | 3 | yes | large |
| E4 | Add control arms that explain *why* memory helps or hurts | 4 | yes | medium |
| E5 | Fix retrieval, then re-measure it without any LLM | 6 | **no** (to measure) | medium |
| E6 | Show what the LLM adds over the detector and a simple retriever | 5 | partly | medium |
| E7 | Re-run the models under one matched setup, plus one local model | 7 | yes | large |
| E8 | Repeat on a second dataset, and test with SHAP switched off | 8 | yes | very large |

**E1, E3 and E4 together are the core.** If only one round of new runs is possible, it should be
E1 + E3 + E4 on Gemma 4 26B (see §8).

---

## 2. Rules every new run must keep

These come from `CLAUDE.md` and apply to every experiment below.

- **Arm B is still Arm A plus memory.** Every new arm (E4) must be a setting on the memory module, never a
  second triage codepath. No `if arm == ...` outside `src/memsoc/memory/`.
- **One prompt for all arms.** Any prompt change (E6, E8) applies to every arm of that comparison, in one commit.
- **Decide before you look.** Choose the retrieval method (E5), the benign sample (E1) and the alert orders
  (E3) **before** any LLM run, and write the choice down. Never change them after seeing results.
- **Never overwrite a run.** New runs get new run ids. The existing `-p1`/`-p3` runs stay as they are.
- **Follow a written protocol.** New runs need a protocol v4 (same idea as v3: tagged code, preflight,
  `--verify`), so every model runs the same way. This also fixes the problem in E7.

### Protected components these experiments touch

Several experiments change something `CLAUDE.md` lists as frozen. **Each one needs explicit team approval
before any code changes.** A plan is not approval.

| Experiment | Protected component | What would change |
|---|---|---|
| E1 | Detector thresholds (if the "lower the threshold" option is chosen) | Prefer the other option: send benign flows to the LLM directly, leaving the detector untouched |
| E3 | Alert stream order and seeds | New, declared orders on top of `SEED = 42`. `SEED` itself must not change or become configurable |
| E5 | Embedding model | Swapping or adding a retrieval method changes the memory layer's similarity measure |
| E6 | Base prompt template | A static-knowledge arm adds text to the prompt |
| E8 | Detection model, prompt | A second dataset needs a second detector; SHAP-off removes part of the prompt |
| all | Evaluation harness | New metrics (E1) must be added as new code, without changing how existing metrics are computed |

---

## 3. Decisions the team must make first

Nothing in §4–§7 can start until these are answered. Each is a research decision, not an implementation one.

| Decision | Options | Blocks | Backlog |
|---|---|---|---|
| D1. How do benign flows reach the LLM? | (a) send a sample of benign flows to the LLM as if flagged (detector untouched); (b) lower the detector threshold so it raises false alarms (changes a frozen component) | E1 | BL-016, BL-143 |
| D2. What does the LLM see as the detector's label for a benign flow? | the multiclass model's guess run anyway; or "no family", which tells the model the answer | E1 | BL-143 |
| D3. How many benign alerts, in what mix? | e.g. as many benign as attacks; or the real ~99% benign share (very expensive) | E1, cost | — |
| D4. The cost-weighted metric: how much worse is a missed attack than a false alarm? | team must state the weight; it may not be picked after seeing results | E1 | BL-105 |
| D5. Which retrieval method do all new memory runs use? | current text embedding; hybrid keys; numeric features; a new embedding model | E3, E4, E7 | BL-111, BL-112 |
| D6. How many alert orders, and how are they drawn? | 5–10 orders, alerts sampled at random within each family | E3 | BL-098 |
| D7. Which models? | Gemma 4 26B (fast on the free tier); gpt-oss-20b (slow on Groq's quota); drop Qwen or re-run it; one local model | E3, E4, E7 | BL-144 |

---

## 4. Experiments that need no LLM calls

These are quick and should go first. They can change what the LLM experiments look like.

### E2. Re-check the detector for near-duplicate leakage (review point 1)

**Why:** a detector with zero false alarms and zero misses on 120,000 held-out flows looks too good. The
earlier stream was 82% training data.

**Already done:** BL-025 compared rows by a hash of their 48 model features, so **exact** copies of training rows
are already counted as leaked. **Near**-duplicates were never checked.

**What to run:**
1. Group train and held-out rows by near-duplicate patterns, such as the same source/destination/port/protocol
   pattern with similar volumes.
2. Remove held-out rows that have a near-twin in the training data.
3. Re-score the frozen detector on what is left.

**Report:** detector binary recall, false-alarm rate and family accuracy with and without that removal.

**Cost:** detector inference only; no API calls.
**Backlog:** BL-157.

### E5. Fix retrieval, then measure it without any LLM (review point 6)

**Why:** the closest stored case has the right family only 58.7% of the time, and 15.2% on the 282 alerts the
detector gets wrong, which is worse than chance (23.3%). Similarity scores of right and wrong matches are the
same (about 0.997). The numeric-feature variant did not fix it.

**What to run:** score each candidate method with the existing past-only precision-at-k test, over all 1,135
alerts, before any LLM run.
- **Hybrid keys:** filter by detector label and protocol/port, then rank by text or numeric similarity.
- **Top-SHAP-feature keys:** match on the features the detector itself relied on.
- **A different embedding model**, e.g. `bge-small-en-v1.5`, or one trained on this data without labels.
- **BL-112:** numeric bucketing with thresholds from flagged traffic only.

**Report:** P@1/2/3 overall and on the hard cases, beside chance; the similarity of right and wrong matches.

**Rule:** pick the method on these numbers alone (decision D5), then freeze it. Do not pick it from LLM results.

**Backlog:** BL-111, BL-112, BL-014.

### E6a. Baselines that need no LLM (review points 1 and 5)

Put these next to every arm in every results table:

- **Always escalate:** it scores 100% recall on the current stream, so it shows recall's limit.
- **Detector only:** the detector's own verdict and family.
- **Detector plus simple rules:** for example, escalate when the detector's confidence or a top SHAP value is
  above a fixed cut-off. Fix the cut-off before looking at results.
- **kNN vote over true labels:** the label most common among the retrieved neighbours. The capstone report
  §4.8 already has this for the text embedding; redo it for whatever retrieval E5 picks.

**Backlog:** BL-019, BL-160.

---

## 5. Experiments that need LLM calls

### E1. Add benign traffic (review point 1) — the most important one

**Why:** with only real attacks, an "always escalate" policy is perfect, so a recall gain cannot show better
judgement. The project's actual aim, fewer unnecessary escalations, cannot be measured at all.

**What to run:** a mixed stream of attacks and benign flows, as decided in D1–D3, through arms A and B-self at
minimum.

**Report:**
- **Basic rates:** the false-alarm rate (benign flows the LLM escalated), recall and balanced accuracy.
- **Cost-weighted score:** using the weight from D4.
- **Family accuracy:** on attacks only.

**Watch for:** benign flows now go through the same memory, so B-self can also copy a wrong "attack" answer
onto harmless traffic. That is part of what this experiment measures.

**Note:** `false_positive` already exists as a verdict, so the verdict schema needs no change for
escalate/dismiss. It changes only if the team also wants an escalation-priority field (BL-106, blocked).

**Backlog:** BL-016, BL-143, BL-105.

### E3. Several runs, in different alert orders (review point 3)

**Why:**
- In the memory arms, each verdict changes the ones after it, so alerts are not independent.
- The first 165 alerts start with Fuzzers, and B-self then labelled all 143 of its escalations Fuzzers.
- One run in one order cannot tell a real effect from the luck of which alert came first.

**What to run:**
- 5–10 different alert orders (decision D6), each a random sample stratified by family, not the first 165.
- Every arm in every order.
- If the budget allows, one order at three lengths (165, 500 and all 1,135 alerts), to see whether the effect
  grows or fades.

**Report:**
- The mean and spread of every measure across orders.
- A test that treats the order, or the near-duplicate group, as the unit: a permutation test or a group
  bootstrap. Keep McNemar only as a count of fixed and broken alerts.

**Backlog:** BL-158, BL-098.

### E4. Control arms that explain the mechanism (review point 4)

**Why:**
- The paper says the harm comes from *what memory stores*. But B-oracle differs from B-self only in having the
  true labels, so it also works like a nearest-neighbour classifier with correct answers.
- It does not separate three possible causes: the stored label, merely having precedents in the prompt, or the
  order they arrive in.
- The paper also states "store the verdict only" and "store only confident answers" as conclusions, although
  neither was tested.

**What to run:** these arms, each a setting of the memory module, on the same alerts and orders as E3:

| Arm | Memory holds | Tests |
|---|---|---|
| Random-precedent | 3 random earlier cases instead of the 3 most similar | does similarity matter at all? |
| Shuffled-label | the 3 similar cases, with true labels shuffled among them | is it the correct label, or just any label? |
| Label-free | the 3 similar cases with escalate/dismiss only, no attack family | does dropping the family keep the recall gain and remove the labelling harm? |
| Detector-label | the 3 similar cases tagged with the detector's own family | is the model's own label worse than the detector's? |
| Confidence-gated | only cases where the model was confident (cut-off fixed in advance) | does filtering what is written stop the harm? |

**Also:** rename B-oracle to "true-label memory", and call it an upper reference, not a ceiling.

**Backlog:** BL-159.

### E6b. What the LLM adds (review point 5)

**Why:** the detector names the family better than every LLM arm (82.4% on the same alerts), so the paper must
show what the LLM is for.

**What to run:**
- **Static-knowledge arm:** the prompt gets short descriptions of the attack families instead of past cases.
  This shows whether case memory adds anything over ordinary retrieval of reference material. It changes the
  prompt, so it needs approval (§2).
- **Rating the explanations:** people (analysts or senior students) score a sample of rationales from each
  arm without knowing which arm wrote them.
- **Cost and speed:** time, tokens and cost per alert for each arm, from the existing logs.

**Note:** the reviewer's "prompt-only arm with the detector's confidence" already exists as Arm A. The current
prompt shows the detector's family and both confidence scores (`triage_prompt.py:339-340`).

**Backlog:** BL-160, BL-019.

### E7. One matched setup for every model, plus a local model (review point 7)

**Why:** the three runs differ in protocol (v3, v1 with deviations, none), output cap (16,384, 6,000 and
1,000), alert count (165 against 250) and tester, and Qwen has no B-oracle arm. So the cross-model comparison
cannot be trusted.

**What to run:**
- Every model under protocol v4, with the same cap where providers allow it, the same alerts and orders, and
  every arm.
- Re-run Qwen properly or drop it.
- Add one open-weight model run locally (for example Gemma 4 under Ollama), with fixed weights and settings,
  so anyone can reproduce the run.
- Record the exact model id, date and API settings, as `run_config.json` already does.

**Limit:** Gemma ran on AI Studio and the other two models on Groq. If no single free provider serves every
chosen model, "same provider" cannot be met, and the paper should say so.

**Backlog:** BL-144, BL-161.

### E8. Second dataset, and SHAP off (review point 8)

**What to run:**
1. **Second dataset:** repeat on NF-ToN-IoT-v3 or NF-CSE-CIC-IDS2018-v3 with a train/test split by time. This
   needs a new detector trained on that data, which is a new frozen component with its own memory-store
   schema version. It is by far the biggest item.
2. **SHAP ablation:** run arms A and B-self with the SHAP explanation removed from the prompt, for both arms,
   to show whether SHAP changes the verdicts.

**Backlog:** BL-162.

---

## 6. Analyses on the existing logs (no new runs)

The review asks for these too. They use the per-verdict files already in `artifacts/runs/`.

- **Precedent quality:** split B-self and B-oracle results by whether the retrieved cases were the right family.
- **Real examples:** pick right and wrong retrieved cases to show the copying behaviour in the paper.
- **Grouped tests:** group-level bootstrap or permutation tests for Gemma and gpt-oss. The capstone report
  already has the group bootstrap, but its scripts are not in the repo (BL-148).
- **Gemma's effects:** effect sizes with intervals for every comparison.

---

## 7. Budget

These are estimates from measured runs, not promises.

| Model | Measured speed | Free-tier limit | 1,000 calls takes |
|---|---|---|---|
| Gemma 4 26B (AI Studio) | 495 calls in 5 h 18 min, about 39 s per call | 14,400 requests a day (`config.DAILY_REQUEST_LIMITS`) | about 11 hours |
| gpt-oss-20b (Groq) | about 2–3 s per call | 200,000 tokens a day, about 70–130 calls | about 8–14 days |

**Calls = alerts × arms × orders.** Each new arm or order multiplies the total.

**Example (§8 minimum set):** 330 alerts (165 attacks + 165 benign) × 5 arms × 5 orders = **8,250 calls**.
- **Gemma:** about 90 hours of running, around 4 days, well inside its daily limit.
- **gpt-oss-20b:** months on Groq's free tier. Multi-order runs are only practical on Gemma or a local model.

---

## 8. If there is only time for one round

1. **No-LLM work first:** E2, E5 and E6a, then freeze the retrieval method.
2. **One LLM round on Gemma 4 26B only:**
   - a mixed attack-and-benign stream (E1);
   - 5 alert orders (E3);
   - arms A, B-self, true-label, label-free and random-precedent (E4).
3. **Results on the existing logs:** the §6 analyses.
4. **State the rest as limitations:** the cross-model rerun (E7), the second dataset (E8) and the rating of
   explanations (E6b).

---

## 9. Backlog rows

| Experiment | Rows |
|---|---|
| E1 benign traffic | BL-016, BL-143, BL-105 (BL-106 only if a priority field is wanted) |
| E2 near-duplicate leakage | BL-157 |
| E3 orders and repeats | BL-158, BL-098 |
| E4 control arms | BL-159 |
| E5 retrieval | BL-111, BL-112, BL-014 |
| E6 LLM value and baselines | BL-160, BL-019 |
| E7 matched rerun and local model | BL-144, BL-161 |
| E8 second dataset and SHAP off | BL-162 |
