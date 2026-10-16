# Testing Results to Date — Arm A and Arm B Together

> Every test run so far, in one place, so the next step can be chosen.
> **Compiled:** 2026-10-16. Every number here was re-read from the run files on that date. Run files live in
> `artifacts/runs/<run-id>/triage_verdicts.jsonl`; scoring used the unchanged
> `memsoc.triage.score_verdicts`. The notebook is `notebooks/retrieval-quality.ipynb`; its executed copy is
> `artifacts/figures/retrieval-quality.ipynb`.
>
> **Constraint for the next step:** free tiers only. No paid LLM (decisions.md **A4**, confirmed again 2026-10-16).

---

## 1. The short version

1. **The plumbing works end to end.**
   - Detector → memory → LLM → verdict → write-back runs in all three arms from one codepath.
   - It passes its integrity checks: Arm A never touched memory, and both memory arms retrieved identical past cases.
   - All 27 memory and triage tests pass.
2. **Memory finds the right kind of attack about twice as often as chance** (59% against 28%).
   - On the alerts where the detector named the wrong family, it does **worse** than chance (15% against 23%).
   - So memory cannot rescue the detector's own mistakes by similarity alone.
3. **The only complete three-arm test ran on a model that was too weak**: `gemini-3.5-flash-lite`, a stand-in.
   - It called almost every real attack harmless *on its own* (Arm A caught 1 of 165).
   - With its own verdicts in memory (B-self), it caught 0 of 165 and grew *more* confident. That is a clean demonstration of error propagation.
   - With correct labels in the same memory (B-oracle), it caught 146 of 165.
4. **That test cannot answer the main question**, "does memory help a real deployment?". Because the stand-in model starts at the floor, B-self had nothing to improve on.
5. **The decided model, `gemini-3.8-flash`, looks much stronger**: 9 of 10 attacks escalated across its first few verdicts. But its free quota is **20 requests a day**, so the full test would take about 170 days.
6. **The next step is a choice of free model.**
   - Four free models that have not yet been tried answer through our existing code with no changes: **Gemma 4 26B-A4B, Gemma 4 31B, Gemini 3.6 Flash, Gemini 3.1 Flash-Lite**.
   - Their daily limits are not published. They are shown only on the AI Studio rate-limit page, which is a one-minute check. Section 8 lays out the options.
   - **Decided later the same day:** three testers run three free models (gpt-oss-20b and qwen3.8-27b on Groq, Gemma 4 26B on AI Studio) on the first 165 alerts, all three arms, under [`testing-protocol-v1.md`](./testing-protocol-v1.md) (decisions.md B5, BL-122).
   - **Update, same day (§7a–7b):** limits were read from AI Studio and three models were checked on 5 real alerts. **Only Gemma 4 26B is usable and off the floor** (14,400/day, ~45 s per alert, 3/5 attacks escalated). Gemma 4 31B is too slow and overloaded. 3.1 Flash Lite is at the floor (0/5). Our own request counter would cap any Gemma run at 480/day (BL-121).

---

## 2. What is being compared

| Arm | What the LLM sees | Memory | Role |
|---|---|---|---|
| **A** | the alert only | off; no store is ever created | baseline |
| **B-self** | the alert + its 3 most similar *past* alerts, each with **the LLM's own earlier verdict** | written after every alert, right or wrong | **the headline**, the deployable system |
| **B-oracle** | the alert + the same 3 past alerts, each with **the true label** | written after every alert from ground truth | a declared **ceiling**, never the headline |

All three use the same prompt template, LLM call, parser, logging and scorer. The only differences are the retrieve-and-inject step and the write-back step. With no past cases, the prompt is byte-identical to the Arm A prompt (SHA-256 pinned in `tests/test_triage_memory.py`).

**Fixed settings in every run:**

| | |
|---|---|
| Stream | stream v2, held-out rows only, `SEED = 42`, 120,000 flows |
| Detector | frozen LightGBM + SHAP, untouched |
| Embedding | `all-MiniLM-L6-v2` @ `1110a243…`, CPU, 256-token limit enforced (raises, never truncates) |
| Vector DB | ChromaDB 1.5.9, on disk, a fresh store per run, cosine, **top 3, no similarity cut-off, write every case** |
| Case text | template 1.0: the alert's features plus the detector's top-3 SHAP feature names, no verdict (decisions.md C1) |
| LLM | temperature 0; the model is recorded in every verdict row |

---

## 3. Timeline of everything tested

| Date | Test | Model | Data | Scope | Status |
|---|---|---|---|---|---|
| 2026-08-30 | Arm A pilot | Groq `openai/gpt-oss-20b` | stream v1, 5,000 flows (**contaminated**: 82% training rows) | 40 alerts | Superseded. Not reproducible (decisions.md D3) |
| before 10-10 | Sandbox retrieval test | none (no LLM) | stream v1, 211 alerts (contaminated) | offline | Superseded by §5 |
| 2026-10-10 | Detector re-measured on clean data | none | stream v2, 25,000 flows | 215 alerts | Valid |
| 2026-10-13 | Memory layer built and tested offline | none | stream v2, 215 alerts | offline | Valid |
| 2026-10-14 | Stream extended; first B-self run; smoke runs | `gemini-3.5-flash-lite` | stream v2, 120,000 flows, capture **incomplete** at the time | 165 alerts | Superseded; do not pool |
| **2026-10-15** | **First three-arm run** | **`gemini-3.5-flash-lite`** | **stream v2, 120,000 flows, 1,135 alerts** | **165 paired alerts** | **Valid; the main result so far** |
| 2026-10-16 | Three-arm run on the decided model | `gemini-3.8-flash` | same | 2 / 5 / 3 alerts | Valid but tiny; stopped by the 20/day quota |
| 2026-10-16 | Reachability check of other free models | Gemma 4, Gemini 3.6 Flash, 3.1 Flash-Lite | a one-word prompt, no alerts | — | All answered (§7) |

---

## 4. The detector (Layer 2) — the reference every LLM number is compared to

| Stream | Flows | Real attacks | Flagged | False alarms | Missed | Family named correctly |
|---|---|---|---|---|---|---|
| v1, 5,000 (contaminated) | 5,000 | — | 211 | 1 | 0 | 89.0% (187/210) — inflated |
| v2, 25,000 | 25,000 | 215 | 215 | **0** | **0** | **76.3%** (164/215) |
| **v2, 120,000 (current)** | 120,000 | 1,135 | 1,135 | **0** | **0** | **75.2%** (853/1,135) |

- **What this means for the LLM test:** every alert the LLM sees is a real attack.
  - "Escalate" is therefore always the right call, and "dismiss" is always a miss.
  - The detector's mistakes are all about **which family** of attack it is: 282 of 1,135, the "hard cases".
- **Alert families (1,135):** Exploits 468, Fuzzers 328, Reconnaissance 131, DoS 68, Generic 59, Backdoor 45, Shellcode 23, Analysis 12, Worms 1.
- The zero false-alarm rate is structural: no harmless flow scores anywhere near the 0.50 threshold (decisions.md B1). So the brief's "reduce false positives" cannot be measured at the detector, and B1 moved the headline to unnecessary escalations (§9).

---

## 5. Memory retrieval quality — no LLM involved

This asks one question: when memory pulls up the most similar past alert, is it the same attack family?

### 5a. Offline, over all 1,135 alerts, past alerts only (`notebooks/retrieval-quality.ipynb`, Figures 2–5)

| | All attacks | Hard cases (detector wrong, n=282) |
|---|---|---|
| Nearest past alert is the same family | **58.7%** | **15.2%** |
| Random past attack is the same family (chance) | 27.5% | 23.3% |
| Detector names the family correctly | 75.2% | 0% (by definition) |
| Top-3 past alerts, share the same family | 57.1% | 14.3% |

- **Similarity scores cannot tell a good match from a bad one.** Correct and wrong nearest matches both have a median similarity of about 0.997, which is why there is no cut-off (decisions.md C8).
- **Case text fits the embedding model:** about 121 tokens median and 143 max, against the 256 limit (Figure 1).
- **The older sandbox test** (contaminated stream) found 64% against 29% chance, and 21% on its hard cases. The pattern is the same; the clean numbers above replace it.

### 5b. Live, inside the 2026-10-15 run (memory filling as the run went)

| | Top-1 same family | Chance | n |
|---|---|---|---|
| All alerts | **56.6%** | 26.6% | 166 |
| Hard cases | **10.3%** | 21.4% | 29 |
| First 100 alerts (memory filling) | 53.5% | 26.4% | 99 |
| After 100 alerts | 61.2% | 26.5% | 67 |

- 99.4% of alerts retrieved at least one past case. The only one that didn't is the very first alert, when memory is empty.

**Reading:** retrieval works about twice as well as chance overall, and is worse than chance exactly where the detector fails. Whatever help memory gives comes from what it stores *about* past alerts, not from finding the right past alert on hard cases.

---

## 6. Arm A and Arm B results

### 6a. The main result — 2026-10-15, `gemini-3.5-flash-lite`, 165 alerts triaged by all three arms

- **Runs:** `armA-flashlite-20261015`, `bself-flashlite-20261015`, `boracle-flashlite-20261015`.
- **When:** side by side, 12:40–13:17 UTC (18:10–18:47 IST).
- **Coverage:** stopped by the 500-requests-per-day free quota at 167, 167 and 165 alerts. The 165 alerts all three arms share are the first 165 in stream order.

| Measure | Arm A (no memory) | B-self (own verdicts) | B-oracle (true labels) |
|---|---|---|---|
| Real attacks escalated | **1 / 165 = 0.6%** [0.1–3.4] | **0 / 165 = 0.0%** [0.0–2.3] | **146 / 165 = 88.5%** [82.7–92.5] |
| Real attacks dismissed as harmless | 164 | 165 | 19 |
| Attack family named correctly | 0.6% [0.1–3.4] | 0.0% [0.0–2.3] | **67.3%** [59.8–74.0] |
| *Detector, same 165 alerts* | *82.4%* | *82.4%* | *82.4%* |
| Mean stated confidence | 0.88 | **0.94** | 0.92 |
| Agrees with detector's family | 0.6% | 0.0% | 81.2% |
| Same verdict on near-duplicate alerts (17 groups) | 94.1% | 100% | 35.3% |
| Median time per alert | 3.8 s | 3.9 s | 3.7 s |
| Past cases shown per alert | 0 | 2.96 | 2.96 |

*[ ] = 95% Wilson interval.*

**Paired test against Arm A** (exact McNemar, the same alert in both arms):

| Comparison | A right, B wrong | A wrong, B right | p |
|---|---|---|---|
| B-self, escalation | 1 | 0 | 1.0 — no detectable difference |
| B-self, family | 1 | 0 | 1.0 |
| B-oracle, escalation | 0 | 145 | 4.5 × 10⁻⁴⁴ |
| B-oracle, family | 0 | 110 | 1.5 × 10⁻³³ |

**Escalation by true family (escalated / alerts):**

| Family | n | A | B-self | B-oracle |
|---|---|---|---|---|
| Exploits | 64 | 0 | 0 | 56 |
| Fuzzers | 45 | 0 | 0 | 39 |
| Reconnaissance | 31 | 1 | 0 | 30 |
| DoS | 8 | 0 | 0 | 5 |
| Generic | 8 | 0 | 0 | 8 |
| Backdoor | 3 | 0 | 0 | 3 |
| Shellcode | 3 | 0 | 0 | 2 |
| Analysis | 3 | 0 | 0 | 3 |

**Does memory get followed? (Notebook, cell "fixed/broke")**

- **B-self** answered the same as the top past case on 100% of alerts.
  - Every stored label was wrong, so it fixed nothing.
  - It broke the one alert Arm A had escalated.
- **B-oracle** followed memory on 68.3% of alerts. It never broke an alert Arm A had right.
  - When the top past case was the right family (92 alerts), it fixed 86 escalations and 85 family names.
  - When the top past case was the wrong family (72 alerts), it still fixed 59 escalations, because "it's an attack" carried over even when the family did not. It fixed only 25 family names there.

**Integrity checks, all passed:**
- One model across all three arms.
- Arm A retrieved nothing and created no store.
- B-self and B-oracle retrieved the identical past alerts, in the same order, for 165 of 165 alerts.
- The official `score_verdicts` command-line output agrees with the notebook.

### 6b. The decided model — 2026-10-16, `gemini-3.8-flash`

- **Runs:** `armA-g38flash-20261016`, `bself-g38flash-20261016`, `boracle-g38flash-20261016`.
- **Why so few:** the free quota is 20 requests per day, and it was used up by 10:48 IST. All three runs are kept and can resume.

| Alert # | True family | Detector | Arm A | B-self | B-oracle |
|---|---|---|---|---|---|
| 0 | Fuzzers | Fuzzers | **escalated**, Fuzzers, 0.90 | **escalated**, Fuzzers, 0.92 | **escalated**, Fuzzers, 0.92 |
| 1 | Fuzzers | Fuzzers | dismissed, none, 0.90 | **escalated**, Fuzzers, 0.82 | **escalated**, Fuzzers, 0.85 |
| 2 | Exploits | Exploits | — | **escalated**, Exploits, 0.80 | **escalated**, Exploits, 0.85 |
| 3 | Exploits | Exploits | — | **escalated**, Exploits, 0.90 | — |
| 4 | DoS | DoS | — | **escalated**, Exploits, 0.85 | — |

- **Totals:** escalated A 1/2, B-self 5/5, B-oracle 3/3. Family correct A 1/2, B-self 4/5, B-oracle 3/3.
- **Median time per alert:** about 9–24 s, including waits on "high demand" (503) retries.
- **On alert 1, B-self escalated what Arm A dismissed**, with one past case in memory. This is the first sign of memory *helping* rather than hurting, **but it is one alert.** At this size the numbers prove nothing.
- What they do show is that this model is **not at the floor**: it escalates real attacks on its own. That is the condition B-self needs before it can show an improvement.

### 6c. Earlier runs, kept for the record only

| Run | Model | Result | Why it is not used |
|---|---|---|---|
| 2026-08-30 pilot, Arm A, 40 alerts | Groq `gpt-oss-20b` | escalated 12/40 = **30%** [18–45]; family 20% (8/40); detector 82.5% on the same alerts; mean 2.7 s per alert | Contaminated stream; prompt and data predate stream v2; re-running 2 verdicts flipped one (D3) |
| `bself-flashlite-20261014`, 165 alerts | `gemini-3.5-flash-lite` | escalated 0/165 | Ran on an incompletely captured stream; replaced by 6a |
| `smoke-*` (4 runs) | flash-lite, 3.5-flash, 3.7-flash | 0–5 verdicts each | Connectivity checks only |

**Worth noticing:** the August pilot model (`gpt-oss-20b`) caught 30% of real attacks with no memory, and flash-lite caught 0.6%. Model choice moves the baseline far more than anything else measured so far.

---

## 7. LLM access — what was tried and what it allows (free tiers)

| Model | Reached? | Speed seen | Free daily limit | Full test (3 arms × 1,135 = 3,405 calls) |
|---|---|---|---|---|
| `gemini-3.8-flash` (decided, B5) | yes, with intermittent 503s | 4–24 s | **20 / day** (measured from Google's 429) | ~170 days |
| `gemini-3.7-flash` | yes | 60–133 s per alert | not measured | too slow |
| `gemini-3.5-flash` | 503 on a real prompt | — | not measured | — |
| `gemini-2.5-flash` | 404 for new users | — | — | — |
| `gemini-3.5-flash-lite` (stand-in) | yes | ~4 s | **500 / day** (measured) | ~7 days, but the model is at the floor |
| **`gemma-4-26b-a4b-it`** | **yes, 2026-10-16** | 2.3 s (one-word reply); 4.1 s in JSON mode | **not published; check AI Studio** | depends on limit |
| **`gemma-4-31b-it`** | **yes, 2026-10-16** | 67 s (one-word reply, likely queueing) | not published | depends on limit |
| **`gemini-3.6-flash`** | **yes, 2026-10-16** | 4.1 s (one-word reply) | not published | depends on limit |
| **`gemini-3.1-flash-lite`** | **yes, 2026-10-16** | 1.5 s (one-word reply) | not published | depends on limit |
| Groq `openai/gpt-oss-20b` | **no: the key in `.env` is rejected (HTTP 401) as of 2026-10-16** | ~1 call/min (8,000 tokens/min limit, measured in August) | 1,000 / day (August) | ~2.3 days for A + B-self, ~3.4 days for all three; needs a new free key |
| Local (Ollama, this laptop, CPU only) | not installed | estimated, unmeasured | none | 3–4B model: 13–23 h; 8B: 33–55 h |

**Notes:**
- **The four newly reached models** were tested only with a one-word prompt. No alert was sent, so nothing is known yet about their verdicts.
- **Gemma 4 26B-A4B accepts the JSON response mode** our client uses. Any of the four runs through `call_gemini()` unchanged; only the `GEMINI_MODEL` setting differs.
- **Google's rate-limit page publishes no free-tier numbers.** It points to AI Studio, so the daily limits must be read there: https://aistudio.google.com/rate-limit.
- **Gemma 4 is also an open-weights model.** The same model could later be re-run on this laptop under Ollama. That helps reproducibility, which hosted models cannot offer (B5 notes they drift). This is a possibility, not something that has been tested.

### 7a. Free-tier limits, read from AI Studio on 2026-10-16

Source: https://aistudio.google.com/rate-limit, "Free tier", all models. The page's 500/day for 3.5 Flash Lite matches what Google's own 429 reported on 10-15, so these are the key's tier limits. The usage column read 0 for every model, including ones used that day, so the page may have been showing a different project under the same account. The limits are tier-wide either way.

| Model | Requests/min | Input tokens/min | Requests/day |
|---|---|---|---|
| **Gemma 4 26B** (`gemma-4-26b-a4b-it`) | 30 | 16K | **14,400** |
| **Gemma 4 31B** (`gemma-4-31b-it`) | 30 | 16K | **14,400** |
| **Gemini 3.1 Flash Lite** | 15 | 250K | **500** |
| Gemini 3.5 Flash Lite | 15 | 250K | 500 |
| Gemini 3.6 / 3.7 / 3.8 Flash, 3 Flash, 2.5 Flash | 5 | 250K | 20 |
| Gemini 2.5 Flash Lite | 10 | 250K | 20 |
| Gemini 2.5 Pro, 3.1 Pro, 4 Argon | 0 | 0 | 0 (not free) |

Only four text models allow more than 20 requests a day for free, and one of them (3.5 Flash Lite) has already been tested.

### 7b. One-time check of the three picks, 2026-10-16

**Picks:** Gemma 4 26B, Gemma 4 31B, Gemini 3.1 Flash Lite.

**Method:**
- The first 5 alerts in stream order, as Arm A, through the real code path (`triage_runner.triage_alert`, memory `off`, same prompt, client and parser).
- Alert 0 was sent twice to check that the answer repeats at temperature 0.
- 6 requests per model. Nothing was written to `artifacts/runs/` or `artifacts/memory/`. The raw output is in the job's temp folder, not in the repo.

**Pass rules, fixed before running:**
1. Every answer is a valid verdict.
2. It is fast enough for a full run.
3. It gives the same answer twice.

Escalation counts are shown for information only. Five alerts cannot establish a model's quality.

| | Gemma 4 26B | Gemma 4 31B | Gemini 3.1 Flash Lite |
|---|---|---|---|
| Free? | yes, 14,400/day | yes, 14,400/day | yes, 500/day |
| Valid verdict JSON | 6/6 | 6/6 | 6/6 |
| Same answer when asked twice | yes | yes | yes |
| Time per alert (median, incl. retries) | **~45 s** (24–80 s) | **~3.8 min** (81 s–13.7 min; repeated 503 "busy") | ~3 s |
| Real attacks escalated (of 5) | **3** | 2 | **0** |
| Family named correctly (of 5) | 2 | 2 | 0 |
| Full test, 3 arms side by side | ~14 h, fits one day's quota | ~70+ h, unreliable | 7 days (500/day) |
| **Verdict** | **Pass: the only usable one** | **Fails rule 2** (too slow, too many 503s) | **Passes the rules but is at the floor** like 3.5 Flash Lite (0/5) |

Alerts 0–4 are Fuzzers, Fuzzers, Exploits, Exploits, DoS. For comparison, `gemini-3.8-flash` escalated 1/2 (Arm A) on the same first alerts.

**Bottom line:**
- The free list does **not** hold three models that are both usable and above the floor. Only **Gemma 4 26B** is.
- A three-model comparison from free Gemini models alone would be Gemma 4 26B (capable), plus 3.1 Flash Lite and the existing 3.5 Flash Lite run (both at the floor). That is a "strong vs weak model" contrast rather than three comparable models.
- **A blocker before any Gemma run:** `llm_client` keeps one daily counter for *all* Gemini models (`request_budget_gemini.json`), capped by `config.GEMINI_DAILY_REQUEST_LIMIT = 500` minus a reserve of 20. It read 54 after this check, and it would stop a Gemma run at 480 requests a day, against Google's 14,400. Tracked as BL-121.

---

## 8. What the results mean for the next step

### What we can already claim (on 165 alerts, stand-in model)
- **Storing the LLM's unchecked conclusions propagates its errors.** B-self copied its own wrong "harmless" verdict onto every later alert, became more confident, and never recovered. This answers research question 4 (D1), within its limits.
- **What memory stores matters more than what it retrieves.** Both memory arms retrieved identical cases; only the labels differed, and the outcome went from 0% to 88.5% escalated.
- **Even perfect memory did not beat the detector at naming the family** (67.3% against 82.4%).
- **Similarity retrieval is worse than chance on the detector's own mistakes** (15.2% against 23.3%).

### What we cannot claim yet
- **Whether memory helps a real deployment** (B-self better than A). The stand-in model starts at 0.6%, so there was nothing to improve.
- **The headline metric (B1): unnecessary escalations.** It needs the `priority` field in the verdict (BL-106) and the signed-off tier split (BL-105). Neither exists, so no run so far could measure it.
  - For reference only: with the proposed split (86 must-escalate, 79 routine), B-oracle escalated 74 of 86 must-escalate and 72 of 79 routine. It did not reduce routine escalations, but the LLM was never asked to.
- **Run-to-run variation.** B3 asks for 3 runs per arm; there has been one.
- **Anything beyond the first 165 alerts of 1,135.**

### The decisions in front of you

**Decision 1 — which free model runs the test.** It has to be chosen **before** the next run and used in every arm. Choosing a model because its Arm A baseline is stronger works *against* memory, so it is not tuning in Arm B's favour (the same logic as B4). It must be written into decisions.md B5 as a change from `gemini-3.8-flash`.

| Option | Time | Pros | Cons |
|---|---|---|---|
| **A. Gemma 4 26B-A4B or Gemini 3.6 Flash via the Gemini API** | Hours to a few days, depending on the AI Studio limit | No code change; fast; free; Gemma is also open-weights | Daily limit unknown until checked; verdict quality unknown until piloted |
| B. Keep `gemini-3.8-flash` at 20/day | ~170 days for everything | The decided model | Not feasible |
| C. Re-run `gemini-3.5-flash-lite` on more alerts | ~7 days | Known limits | At the floor; cannot answer the main question. More of the same |
| D. Groq `gpt-oss-20b` with a new free key | ~2.3–3.4 days | Known to escalate 30% at baseline (contaminated pilot) | Needs a new key; ~1 call/min; limits from August may have changed |
| E. Local model (Ollama) | 13–23 h (3–4B) to 33–55 h (8B), estimated | No quota at all; fully reproducible | Install needed; small models may hit the floor; laptop busy throughout |

**Decision 2 — scope.** Choose between all 1,135 alerts and the first *N* in stream order (for example 300 or 500). Memory arms must run in stream order, so a smaller scope is always "the first *N*", never a random sample.

**Decision 3 — the headline metric.** Do you want unnecessary escalations (B1) measured in the next run?
- **If yes:** the `priority` field (BL-106) and the tier split (BL-105) must be approved and added to the prompt **before** the run. That is a protected-component change, and it applies to both arms in one commit.
- **If no:** the next run measures escalation recall and family accuracy only, as 6a did.

**Decision 4 — B-oracle.** Run all three arms, or A + B-self only? B-oracle is the ceiling; dropping it saves a third of the calls.

### Recommended path (free only)
1. **Today, one minute:** open https://aistudio.google.com/rate-limit and note the requests-per-day limit for `gemma-4-26b-a4b-it`, `gemma-4-31b-it`, `gemini-3.6-flash` and `gemini-3.1-flash-lite`.
2. **Pilot, Arm A only, first 20 alerts, on the one or two candidates with the most daily headroom.** About 20–40 requests.
   - Pass criteria, fixed now, before seeing the results:
     - it returns valid verdict JSON on every alert;
     - it escalates a meaningful share of real attacks on its own, i.e. it is not at the floor like flash-lite;
     - it fits the daily limit.
   - Record the choice in B5.
3. **Decide 3 and 4 above**, then run A + B-self (+ B-oracle) side by side under new run IDs, in stream order, resuming across days if the limit requires it.
4. **Re-execute the notebook** on the new runs. Section 6a's tables, the McNemar tests, and the fixed/broke analysis then come out automatically.

---

## 9. Open items that affect these results

| Backlog | What |
|---|---|
| BL-016 | Only flagged flows reach the LLM, so all alerts are real attacks and LLM false positives cannot be measured |
| BL-017 | Sample size and repeats (B3: all alerts, 3 runs per arm) not yet met |
| BL-018 | Prompt strength (B4) never compared; the baseline may be weaker than it needs to be |
| BL-105, BL-106 | Tier split and `priority` field — needed for the B1 headline |
| BL-113 | Oracle cases look different from self cases beyond the label (confidence 1.00, no rationale) |
| BL-117 | Gemini free-tier availability and limits |
| BL-118 | Status of the three-arm run |
| BL-119 | The scorer prints a stale detector baseline of 0.881 (it is 0.752 on the current stream; the per-run "detector, same alerts" line is correct) |
| BL-120 | The Groq key in `.env` is rejected (401) |

Also worth noting: decisions.md **E2** records the paper as due 14 October, which has passed. The new date determines which of the options in §8 fit.
