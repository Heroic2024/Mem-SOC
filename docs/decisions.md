# Decisions — the file that steers this project

Every question this project still has to answer, in the order it has to be
answered. Four are already answered; those come first so nobody re-opens them.

**How to use this file.** Find the question. Read the recommendation. Decide.
Then write the answer and the date into this file. A decision made in a
conversation and not written here is not a decision.

**Last updated:** 2026-10-22

**Read Part F first.** The experiments are finished. Part F records the three
runs that actually happened and what they answered. Parts B and C below are the
questions as they stood *before* those runs; each now carries a status line
saying what became of it. Where a question is still open, it is open **after the
fact** — the run went ahead without it.

---

## The words you need

| Term | What it means here |
|---|---|
| **Detector** | The trained model that flags a network flow as an attack. It is finished and must not be retrained. |
| **Arm A** | The LLM triages each alert on its own. No memory. |
| **Arm B** | The same LLM, same prompt, but it can also look up similar past alerts first. |
| **Memory** | A database of past alerts and what the LLM concluded about them. |
| **True labels** | The dataset's own answer key. Used to mark the LLM's work afterwards. |
| **Alert** | One flow the detector flagged. Only flagged flows currently reach the LLM. |

---

## Numbers you need

All measured, not estimated. All from the **held-out stream** (`stream_version 2`,
rebuilt 2026-10-10), which no longer has the problem described in **A1**.

> **Superseded 2026-10-14 — these are the 25,000-flow figures.** The replay was
> re-run at **120,000 flows** (same `stream_version 2`, same seed 42, set through
> `MEMSOC_SAMPLE_SIZE`), and it flags **1,135** alerts. The 25,000-flow pair is in
> `artifacts/backup-20261014/`. Every published result comes from the **first 165**
> of those 1,135.
>
> So the counts below — 215 alerts, 121 must-escalate, 94 noise, 56.3% escalation
> precision, 164 of 215 families named correctly — describe a sample that no
> reported result uses. They are kept rather than deleted, because **B1**'s whole
> argument is built on them and it is the ratios that carried over. Do not quote a
> count from this section in the paper. Tracked as **BL-118**.

- The detector flagged **215** flows out of 25,000. Of those, **215 were real attacks, 0 were false alarms, and it missed nothing.**
- It named the attack type correctly for **164 of 215**. So **51 were the wrong type.**
- **The false-alarm rate is zero, and that is structural rather than a sample-size problem.** Of 24,785 harmless flows, the closest one to being flagged scored 0.0001 against a 0.50 threshold, and 99.98% scored 0.0000. Nothing at all sits between 0.01 and 0.50. Streaming 15× more flows would still give about zero, so **more logs cannot create false alarms.** See **B1**.
- **Of the 215 real attacks, 121 are families that warrant waking an analyst and 94 are routine scanning noise.** Escalating everything is therefore only **56.3%** precise, leaving **94 unnecessary escalations** to remove — the largest piece of headroom in the project. This is the new headline measure; see **B1**.
- **395,138** rows of the dataset were never used for training. The usable pool, after the rows the detector cannot score are removed, is **385,277** rows holding **3,713** attacks.
- The old figures (211 alerts of 5,000, 187 of 210 correct, 1 false alarm) came from a stream that was **82% training data** — 173 of its 211 alerts. They are superseded, and kept only to show what the contamination was worth: attack-type accuracy fell **12.8 points** once it was removed.
- Pilot run of 40 alerts, 2026-08-30: the LLM agreed with the true labels on **12**, and called **28 real attacks harmless.** That run cannot be reproduced.
- Sandbox test on the 211 alerts: the most similar past alert had the right attack type **64%** of the time. Random guessing gets 29%. The detector gets 89%. **On the 23 the detector got wrong, it was 21% — no better than guessing.** (23, not 24: one of the 211 was a false alarm with no true attack type to name. Also measured on the contaminated stream, so it needs redoing — held out there are **51** to retrieve against.)
- The draft description format for a stored alert was **too long for the embedding model**: 179 of 211 were silently cut short. A shorter format of the same information fits with room to spare.

---

## Do these three things next

> **Closed 2026-10-22.** Kept as written for the record; the bold line under each
> item is what became of it. The runs themselves are in **Part F**.

Steps 1–3 are **done, 2026-10-10.** The backup is at `artifacts/backup-20261010/`
with checksums; the stream was rebuilt from verified held-out rows only; the
detector was re-run and re-measured; **B1 is answered below.**

**These three run in parallel. None of them waits on another.** An earlier
revision of this list was numbered in a way that implied the memory layer came
last; it does not, and that reading cost time.

**A — Build the memory layer. Start now; nothing blocks it.** It does not exist
— zero lines — it is the research variable, and it is the longest remaining job,
so it sets the critical path. It needs no LLM calls and no sign-off: every design
question it depends on is answered in Part C, the specs are written in
`docs/memory-layer/`, and it is built and tested offline against the 215 alerts
that already exist. The `priority` field in **A1** below does not gate it either —
the embedding text is the alert only (**C1**), so a verdict field is one more
metadata key, not a dependency. Tracked as **BL-002**.
**Done 2026-10-13** — `src/memsoc/memory/`, wired into triage the same week.

**B — Record the real rate limits** for the chosen provider: requests/minute,
requests/day, tokens/day, read off the dashboard rather than the documentation.
This gates *running* the scored comparison, not building any of it. It is the
only thing still deciding whether the planned run fits. Tracked as **BL-098**,
**BL-099**, **E1**.
**Answered the hard way.** The limits were never read off a dashboard; they were
hit during the runs and written down afterwards — 20 requests a day on
`gemini-3.8-flash` (BL-117), a 200,000 tokens-per-day ceiling on Groq (BL-135).
The planned run did **not** fit, which is why the scope became 165 alerts across
three free models rather than 1,135 on one. BL-098 stays open as the bookkeeping
task it always was.

**C — Approve the two sign-offs B1 needs**: the `priority` field in the verdict
JSON (**BL-106**) and the escalation tier split (**BL-105**). These gate the
prompt template and the scorer — Workstream 3 — and the prompt is a protected
component, so nobody may edit it until the first is signed off. Neither touches
Layer 3.
**Not done — and all three runs went ahead without them.** BL-106 is `blocked`,
BL-105 is `open`. The consequence is in **B1**: the headline metric this project
declared was never measured, and cannot be recovered from the runs that exist.
It is the largest open item in the project.

---

# Part A — Answered 2026-10-01

Do not re-open these without a written reason.

### A1. The detector was tested on its own training data. What do we do?

**Answer: rebuild the stream using only rows the detector never saw.**

82% of the stream — 4,120 of 5,000 flows, and 173 of the 211 alerts — was in the
detector's training set. The cause is that the stream generator picks rows from
the whole dataset and knows nothing about the 80/20 split used for training.
470,122 untrained-on rows are available.

The detector is **not** retrained. Only the choice of rows to replay changes.

Consequence: the current 211 alerts, the 75-alert sample, the 40 pilot verdicts
and the sandbox retrieval numbers were all computed on mixed data and have to be
redone. Backed up first, not deleted.

Tracked as BL-025 — **done 2026-10-10.** The train/test split had never been
saved and had to be recovered first; the recovery was proved by reproducing the
detector's published fingerprint exactly, including all nine per-class scores and
an order-sensitive 72-of-100 check (**BL-028**). The stream now draws only from
verified held-out rows, and every record carries the dataset row it came from, so
the claim is checkable after the fact. The detector was not retrained.

**BL-022** is still open: the generator still overwrites its own output files with
no warning. Back up before regenerating.

### A2. Do we build the memory layer and run the comparison, or write up the baseline only?

**Answer: build it and run the comparison, cut to the minimum that holds up.**

The mentor's review says a paper that asks whether memory helps and then only
reports the no-memory arm would be rejected. So the comparison has to happen.

Minimum scope: one LLM, one prompt version, 3 repeat runs per arm. Dropped for
now: a second LLM, few-shot prompting comparison.

Answer: Using one LLM, we will try with different ways of storing the cases in the vector database

### A3. What goes into memory — the LLM's own conclusions, or the true answers?

**Answer: both, as two separate conditions.**

- **Main condition:** memory stores what the LLM concluded, right or wrong. Every headline number comes from this.
- **Second condition:** memory stores the true labels instead. Reported separately, clearly marked, and **never** as the headline.

The difference between the two is the cost of storing unchecked work — which the
project brief requires us to measure rather than just warn about.

Ruled out: using the true labels as the *only* thing memory stores. That hands
the LLM the answer key and makes the whole study meaningless.

The two conditions are one switch on the memory module, not two separate sets of
code.

Full reasoning, including what was rejected and why, is in
[`memory-layer/07-open-questions.md`](./memory-layer/07-open-questions.md) OQ-2.
Build work is BL-015.

Answer: Experiment with 2 ways:

-  store only LLM verdicts

- store a mix of llm verdicts and ground truth

**Settled 2026-10-10 — three conditions, one switch, and the mix is dropped.**

A proposal came up to give each of the three of us one memory variant to
build: one stores LLM verdicts, one stores a mix, one stores the true labels.
**Rejected — and note this question was already answered above**, in the
sentence "the two conditions are one switch on the memory module, not two
separate sets of code," and in the line ruling out true-labels-only. The full
reasoning is in [`work-split.md`](./work-split/work-split.md); the short version is that
three separately-written memory layers give three codepaths, and then a
difference in results could come from a difference in implementation rather
than from the memory. That is the one thing that would make the whole
comparison unattributable.

The conditions we run:

| Condition | Memory holds | Status |
|---|---|---|
| **Arm A** | nothing | Baseline. Required. |
| **Arm B-self** | the LLM's own past verdicts, right or wrong | **The headline. The deployable system.** |
| **Arm B-oracle** | the true labels | A declared **ceiling**, never the headline. Run only if budget allows. |

**The "mix" condition is dropped.** A stored case holding both the LLM's
verdict and the true label will be read by the LLM as the true label, so the
mix collapses onto Arm B-oracle. It would have cost a third of the API budget
for a near-duplicate of a condition we were already running.

**If we want a third variant, it should vary the write policy instead** —
write every case, versus only high-confidence ones. That tests memory
poisoning, which is a live risk rather than a hypothetical: BL-014 measured
nearest-neighbour retrieval as *worse than random* on exactly the alerts the
detector got wrong, carrying the wrong attack family 70.8% of the time.
"Does memory poison itself with its own mistakes?" is a stronger contribution
than measuring the oracle twice. Not adopted yet — raise it if Arm B-self
lands early.

Running a condition is a **config change**, made by whoever has API budget
when the module lands. It is not a build task and it is not owned by anyone.
Work is divided by layer instead — see [`work-split.md`](./work-split/work-split.md).

**Status:** answered. Build work is BL-015 (the switch) and BL-002 (the module).

### A4. Free API tier or paid?

**Answer: free: we are not going for the paid version since we do not have the bduget**

*The paragraph below is the recommendation the question was decided against, not
a counter-argument to the decision. It is kept for the record.*

The free tier allows roughly 40 alerts per day in total. The runs this project
needs are in the low thousands of calls. Paying removes the constraint for a
small amount of money and does **not** change which model is used, so nothing
about the experiment changes.

**The decision held, and it shaped the entire experiment.** Every run in Part F
was made on a free tier, and the free tiers are why the scope is 165 of 1,135
alerts (**B3**), one run per arm instead of three (**B3**), three models one per
tester instead of one model (**B5**), and no benign-traffic arm (**B2**). Report
that as a constraint, not as a design choice.

---

# Part B — Answer before spending any money on LLM runs

*The money was spent — in free-tier quota — between 2026-10-15 and 2026-10-22
(**Part F**). Each question below now carries what became of it.*

Changing any of these after a run starts throws that run away. They are the
urgent ones.

### B1. Which single number is the headline result?

**The question:** is the main result "memory reduces false alarms" or "memory
names the attack type correctly more often"?

**Why it matters:** false alarms are what the project brief names as the main
measure, but there is exactly **one** false alarm in 211 alerts — so there is
almost nothing for memory to improve. Attack-type accuracy has 24 wrong answers,
so there is something to improve.

*(Those two figures came from the contaminated stream and are superseded: held
out, it is **zero** false alarms and **51** wrong attack types. The answer below
is the one to read.)*

**Recommendation:** decide this **after** step 2 in *Do these three things next*.
On untrained-on data the detector will make more mistakes of both kinds, and the
original measure may become usable again. Deciding before that measurement means
guessing.

**Status:** **answered 2026-10-10.** Tracked as BL-012, and as BL-105 for the
two sign-offs the answer needs.

**Answer**: try with the other untrained-on data and see how many FPs we get. If we get satisfactory number of FPs, we will go ahead with the testing of the vector database. 

**Answered 2026-10-10 — the headline is the unnecessary-escalation rate.**

The measurement came back and the answer is **zero** false alarms, not a
satisfactory number. Going ahead with the vector database is still right, but
false-alarm *volume* cannot be the headline, for a reason stronger than the count:

- **It is structurally zero, not merely small.** Of 24,785 harmless flows, the nearest one to being flagged scored 0.0001 against a 0.50 threshold, and 99.98% scored 0.0000. There is no near-miss population to draw from, so a bigger sample cannot produce false alarms. The free-measurement route is exhausted.
- **The memory layer could not fix them anyway.** Retrieval happens in the triage layer, *after* the detector has already decided. Even with hundreds of false alarms, memory has no mechanism by which it could remove one. This is an architectural fact, and it was true before any measurement.

So the brief's Objective 1 was never measurable where we were pointing it. It is
measurable one layer up, which is also what the phrase means in ordinary SOC
language: **a false positive is an alert that reached a human who did not need to
see it.**

**The headline number is the unnecessary-escalation rate.** Of the 215 held-out
alerts, **121** are families that warrant waking an analyst (Worms, Backdoor,
Shellcode, Exploits, DoS, Generic) and **94** are routine scanning and probing
noise (Reconnaissance, Analysis, Fuzzers). A system that escalates every alert is
therefore **56.3%** precise (95% CI [49.6%, 62.7%]), leaving **94** unnecessary
escalations on the table. Arm B should remove more of them than Arm A by
recognising precedent — *we have seen twenty of these scans and none mattered* —
without losing any of the 121 that do matter. Both halves get reported:
escalation precision **and** recall on the must-escalate tier, because a system
that escalates nothing would otherwise score perfectly.

That is 94 units of headroom against the 51 the attack-type measure has, it is the
largest in the project, and it serves the objective already submitted to the
mentors.

**Attack-type accuracy stays as the second reported number** (51 errors, already
measured, needs no changes anywhere). Do not drop it — it is the fallback if the
escalation result comes out flat.

**Two things this costs, both needing sign-off before any code moves:**

1. **One new field in the verdict JSON.** The LLM currently answers
   `true_positive | false_positive | inconclusive`, which cannot express *this is
   a real attack but not worth escalating* — and on this stream every
   `false_positive` answer is simply wrong, because all 215 alerts are genuine.
   The metric needs the LLM to state a `priority` of its own. **The prompt
   template is a protected component** (`CLAUDE.md`), so this must be approved
   explicitly, applied identically to both arms in one commit, and versioned so
   that verdicts written under the old wording can never be mixed with the new.
   It also invalidates the 40 pilot verdicts, which **D3** already discards as
   non-reproducible, so nothing further is lost.
2. **The tier split above must be declared, not assumed.** The six/three grouping
   is based on what the attack families *do* — code execution and denial of
   service on one side, scanning and fuzzing on the other. It is defensible, but
   it is a research judgement and it decides the headline number. Confirm it, or
   change it, in writing. Whatever is chosen must be fixed before any scored run
   and reported in the paper as a stated assumption, with the per-class counts
   beside it. Tracked as **BL-105**.

**What this does not change:** the detector, its thresholds, the stream, the seed,
or the two-arm design. The detector's 0 false alarms and 100% recall remain a
reportable result — they are simply not the result memory is being tested on.

**Status 2026-10-22 — declared, never measured. This is the project's largest gap.**

The escalation metric needs the two sign-offs above. Neither arrived:

| Sign-off | Backlog | State |
|---|---|---|
| Declare the escalation tier split in writing | **BL-105** | **open** — the six/three grouping was never confirmed |
| Add `priority` to the verdict JSON | **BL-106** | **blocked** — the prompt is a protected component, the change was never approved, so it was never made |

All three runs in Part F therefore scored what the **unchanged** verdict schema
can express: recall on real attacks, attack-family accuracy, and consistency
across near-duplicate alerts. **No run reports an escalation-precision figure,
and none can be computed after the fact** — the LLM was never asked for a
priority, so the data does not exist.

What that costs: **research question 1 in D1, the one carrying the objective
submitted to the mentors, has no result against it.** There are two honest ways
out and neither has been chosen:

1. **Report recall as the headline** and state plainly that Objective 1 was
   re-scoped mid-project and then not measured, giving the reason above. This
   costs nothing but candour, and the recall result is strong — see Part F.
2. **Run a fourth arm carrying a `priority` field.** Needs BL-105 and BL-106
   signed off first, a prompt-variant bump so old and new verdicts can never be
   pooled (**BL-133**), and free-tier budget that does not exist (**A4**).

**This is a live decision and it is not made.** Whoever presents the work should
settle it before a panel does.

### B2. Do harmless flows get sent to the LLM as well?

**The question:** right now only flows the detector flagged reach the LLM. Should
we also send some it did not flag?

**Why it matters:** if the LLM only ever sees flagged flows, we cannot calculate
a false-alarm rate or produce a confusion matrix at all, and saying "the detector
caught 100% of attacks" is true only because we only showed it attacks. The
mentor's review raises this twice.

**Cost:** roughly doubles the number of LLM calls.

**Recommendation:** yes, include them — but set the number after B1, since B1
decides how much it matters.

**Status:** **re-scoped 2026-10-10**, still open on sample size. Tracked as BL-016.

**Answer**: let us try this as well to create a confusion matrix for understanding. 

**Re-scoped 2026-10-10.** The original reason for this no longer holds: the
detector produces **zero** false alarms on held-out data, so there are none to
feed into triage, and a *detector* confusion matrix would have nothing to put in
two of its four cells.

One reason survives, and it is now the only one: sending harmless flows lets us
measure whether **the LLM itself** over-escalates on traffic no model flagged.
That is a different quantity from the detector's, it is a direct check on the
**B1** headline, and it is the honest answer to the mentor's point that "caught
100% of attacks" means little when only attacks were ever shown.

Keep it, at a sample sized once the rate limits are known, and label it in the
paper as the **LLM** false-positive rate — never the detector's. Tracked as
**BL-016**.

**Status 2026-10-22 — not run.** No benign flow was ever sent to the LLM. This is
limit 1 of every result: with no harmless traffic in the stream, false positives
and true negatives are structurally zero, so the `precision 1.000` the scorer
prints is an artefact of the data and not a finding
(`status/gemma-p3-results.md` §7). BL-016 stays open.

### B3. How many alerts do we triage, and how many times do we repeat each run?

**The question:** 211 alerts? More? And 1 run each or 3?

**Why it matters:** the review says the 40-alert pilot is too small to conclude
anything — its 12-out-of-40 result could honestly be anywhere from 18% to 45%.
It asks for several hundred alerts. Separately, Arm B's result changes from run
to run, because one early mistake gets stored and affects every later lookup, so
a single run is not a measurement.

**Recommendation:** all alerts from the rebuilt stream, 3 runs per arm, varying
only the LLM's randomness and never the order of the alerts. Report a range, not
a single figure, for every number. Compare the two arms alert-by-alert
(a paired test), not by comparing two averages.

**Answer**: go with recommendation, and give me the result

**Status:** open. Tracked as BL-017, and settles half of OQ-6.

**Scoped 2026-10-16 for protocol v1:** the **first 165 alerts** in stream order (the same slice as the 2026-10-15 Flash-Lite run), all three arms, **one run per arm per model**. The free tiers' daily token limits make 1,135 alerts × 3 repeats infeasible. Three repeats remain the target for a later round; this round reports one run per arm and says so.

**Run 2026-10-15 to 2026-10-22 — one run per arm, not three.** Part F has what
each model covered. The three repeats did not happen and are not planned; the
free tiers (**A4**) could not carry them. That leaves exactly the hole B3 warned
about: Arm B's run-to-run variation is **unmeasured**, and because one early
mistake is stored and then retrieved by every later alert, that variation is
expected to be real. Every Arm B number in the write-ups is a single draw and
must be reported as one. BL-017 stays open.

### B4. Which version of the prompt do we use?

**The question:** three options — tell the LLM the detector's answer is correct;
hide the detector's answer; or show it as a guess to check (what we do now).

**Why it matters:** showing it as a guess may be the reason the LLM called 28 of
40 real attacks harmless. If the baseline is needlessly weak, any improvement
from memory looks bigger than it is.

**Recommendation:** test all three on the no-memory arm, pick the strongest, then
freeze it and use the same one in both arms. Making the baseline *stronger* works
against memory, so this is the safe direction to tune in.

**Answer: Go ahead with recommendation**

**Status 2026-10-22 — the comparison was never run, and the prompt was frozen
anyway.** Every run in Part F used `config.PROMPT_VARIANT = "label-hypothesis-v1"`
— option 3, *show the detector's answer as a guess to check*, which is the very
option this question suspects of causing the pilot's 28 misses. Options 1 and 2
were never tested, so the baseline prompt is unjustified by measurement and the
safe-direction argument above was never exercised. This file's own words apply:
"if the baseline is needlessly weak, any improvement from memory looks bigger
than it is." List it as a limitation. BL-018 stays open; enforcing the variant at
scoring time is BL-133.

**Status:** open. Tracked as BL-018.

### B5. Which exact LLM, at which setting?

**The question:** the full model name and version, and the temperature.

**Why it matters:** the review lists these as missing from the paper. Separately,
re-running two pilot verdicts through an identical prompt **changed one answer
and moved the other's confidence**, so the hosted model drifts over time. The
exact identifier and the dates of the runs have to be recorded.

**Recommendation:** temperature 0, one named model and version, both arms run in
the same time window, and model drift listed as a limitation.

**Status:** **answered 2026-10-14** (see the clarification below). Related to BL-009 and BL-099.

**Answer:** gemini-3.8-flash, temperature should be at a higher deterministic leve, balance it so that we can get satisfactory results for the paper

**Clarified 2026-10-14:** `gemini-3.8-flash` on the Google Gemini API, temperature **0**, thinking level left at the model's default. It is used for per-alert triage in every arm; reports stay on Groq. Implemented in `src/memsoc/triage/config.py` and `llm_client.call_triage_llm()`. BL-099 is closed.

**Amended 2026-10-16 — three free models replace `gemini-3.8-flash`.** Its free tier allows 20 requests a day (BL-117), so the full test would take about 170 days. Paid tiers stay ruled out (A4). The test now runs on three free models, one per tester, under the test protocol (v1 on 2026-10-16; **superseded 2026-10-17 by [`docs/status/testing-protocol-v3.md`](./status/testing-protocol-v3.md)**, a parser fix then a per-model output cap, BL-125 and BL-126):

| Tester | Model | Provider |
|---|---|---|
| G | `openai/gpt-oss-20b` (the August pilot's model) | Groq |
| Q | `qwen/qwen3.8-27b` (a Groq *preview* model, so it can be withdrawn) | Groq |
| M | `gemma-4-26b-a4b-it` | Google AI Studio |

The settings are identical for all three: temperature 0; JSON answer mode on both providers; reasoning or thinking at each model's default. Nothing was chosen by looking at Arm B results. Models are compared with each other, never pooled.

**The output cap is per model, not uniform — corrected 2026-10-22.** This line
previously read "a 6,000-token output cap for every model", which neither the
protocol nor the code ever did. `config.TRIAGE_MAX_RESPONSE_TOKENS_BY_MODEL` sets
**6,000** for `gpt-oss-20b` and `qwen3.8-27b` and **16,384** for `gemma-4-26b`;
each run's `run_config.json` records the cap it ran under, and the Gemma run's
reads 16,384. The split exists because a reasoning model can spend a 6,000-token
cap thinking and never answer, which halted tester M's v2 run
([`status/testing-protocol-v3.md`](./status/testing-protocol-v3.md) §0,
**BL-126**). Earlier still, the Qwen run was made at **1,000** (**BL-134**).
Within one model every arm shares one cap, so no A / B-self / B-oracle comparison
is affected; what the split qualifies is comparison **between** models.

**Run 2026-10-17 to 2026-10-22 (Person 2): tester Q's model, `qwen/qwen3.8-27b`, was run and reported** — Arms A and B-self, 250 alerts each, prompt variant `label-hypothesis-v1`. Result in [`status/qwen-results.md`](./status/qwen-results.md): the model is at the floor (Arm A caught 5 of 250, B-self 0), so the run is a valid negative result that cannot answer the research question. See BL-134 and BL-137.

The report path keeps its own Groq model (`GROQ_MODEL`) and is unaffected by the triage model. Verdicts made on different models are never pooled: that includes the 2026-10-15 `gemini-3.5-flash-lite` runs against any Qwen or Gemma verdict.

**All three runs are now done.** Tester M's Gemma run is the complete one and is
the project's terminal result; tester G's `gpt-oss-20b` run completed on protocol
v1; tester Q's Qwen run is a valid negative. See **Part F**.

---

# Part C — Answer before building the memory layer

*The memory layer was built 2026-10-13. C1, C2, C3, C5, C7, C8 and C10 were
settled before it. **C4 and C6 are recorded below, 2026-10-22, from what was
actually implemented** — in both cases the implementation matches the
recommendation, so nothing is being decided retrospectively, only written down.
C9 is answered but **not built** (BL-075).*

None of these cost money. All of them are hard to change later, because the
stored alerts would have to be rebuilt.

Detailed reasoning and rejected options for C1–C8 are in
[`memory-layer/07-open-questions.md`](./memory-layer/07-open-questions.md).
Record the answer in **both** files.

### C1. What text gets stored and compared — the alert only, or the alert plus the LLM's conclusion?

**Recommendation: the alert only.** The conclusion and reasoning are still stored
alongside and still shown to the LLM; they just do not decide which past alerts
come back.

**Evidence:** adding only the detector's one-line answer to the stored text
raised the overall match rate from 64% to 77%, but dropped it from 21% to **4%**
on the 24 alerts the detector got wrong. The overall number improves while the
thing we are trying to measure is destroyed. Storing the LLM's full reasoning
would be a stronger version of the same problem.

**Answer**: if there is space, let us go with the both the verdicts. Else, decide how you want to store it accrodingly. We have to get to the aim.

**Settled 2026-10-13: the alert only, plus the detector's top-3 SHAP feature
names.** "Both verdicts" was ruled out because it cannot work: a new alert has
no LLM verdict yet, so stored cases and queries would be written in different
shapes (`memory-layer/retrieval-precision-investigation.md` §4.3). The
detector's label line is also left out, because it measured worst on the
detector's own errors (§3, §4.1). Verdicts and reasoning are still stored with
every case and shown to the LLM; they just do not decide the match.
Implemented as `schema_version 1.0` in `src/memsoc/memory/case_text.py`.

**Status:** answered 2026-10-13. OQ-1.

### C2. Which embedding model, at which exact version?

**Recommendation:** `all-MiniLM-L6-v2`, the one already named in the brief, **and
pin the exact versions** of the three packages it depends on. The sandbox ran
`chromadb 1.5.9`, `sentence-transformers 6.1.0`, `torch 2.14.0+cpu`,
`transformers 5.17.0`, `numpy 2.5.3`, Python 3.13.2, on CPU.

**Why the pin matters:** a minor version upgrade can quietly change how text is
turned into numbers, which changes which past alerts come back. Once this is
locked it cannot be changed without rebuilding every stored alert.

**Status:** open. OQ-8. The version pin is currently written down **nowhere** in
this repository.

**Answer:** go through the docs\embedding-model-options.md and decide what to go with

**Settled 2026-10-13: `all-MiniLM-L6-v2`**, the recommendation in
`embedding-model-options.md` §5. Its condition was that the case text fits 256
tokens, and it does: template 1.0 measures p50 121, p99 136, max 143 over all
215 alerts. The model is pinned in `src/memsoc/memory/embedding.py` by name, by
Hugging Face commit `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, and to CPU.
The package versions are pinned in `requirements/memory.txt`, and the full
resolved set is in `artifacts/memory-env-freeze.txt`. **Status:** answered
2026-10-13.

### C3. Which description format for a stored alert — the long one or the short one?

**Recommendation: the short one, because it fits.** The long format runs to 273
tokens at the 99th percentile against a 256 limit, so 179 of 211 alerts were cut
short. The short format, carrying the same information, peaks at 162.

The cut is **silent** — nothing warns you. So whichever format is chosen, the
code must check the length and fail loudly rather than trust it.

Both formats scored identically on match rate (64%), so choosing between them on
that basis would be fitting to the test data. "It fits the limit" is the honest
reason.

**Status:** open, measurement done. Tracked as BL-013, recorded under OQ-8.

**Answer:** depends on embedding model, decide which is the best

**Settled 2026-10-13: neither -- template 1.0 replaces both.** It is a short
format (see C1) and fits MiniLM with room to spare (C2). The length check
raises rather than truncating silently. **Status:** answered 2026-10-13.

### C4. Where does the stored attack type come from?

**Recommendation:** the LLM's own answer, kept as a separate field from the
detector's answer. Where the two disagree is itself a result worth reporting.

**Answer** — recorded 2026-10-22 from the implementation, which did what the
recommendation said. A stored case carries `attack_category` taken from the
**LLM's own verdict**, tagged `label_source: "llm"`, and carries the detector's
answer separately as `detector_label` (`src/memsoc/memory/store.py:335`,
`:346-363`). Under the B-oracle condition the same field holds the true label
instead, tagged `label_source: "oracle"` — which is what keeps the two conditions
one switch rather than two codepaths (**A3**). Because both are stored,
disagreement between the LLM and the detector is recoverable from the stores
after the fact.

**Status:** answered 2026-10-22. OQ-3.

### C5. Which alerts get written to memory — all of them, or only confident ones?

**Recommendation: all of them**, for the main result. Filtering out the uncertain
ones hides the error-spreading effect the brief requires us to measure, and it
removes exactly the hard cases where memory might help.

For reference: filtering at a detector confidence of 0.75 would keep 114 of 211
alerts and exclude 20 of the detector's 24 mistakes — tidier memory, but the hard
cases are gone. Do not pick that number off this page; it was measured against
the answer key.

**Status:** open. OQ-5.

**Answer: **  decide this, we need to get results ASAP, let us go ahead with whatever gives us satisfactory results 

**Settled 2026-10-13: write every case (`write_all`)**, as recommended. Note
that "whatever gives satisfactory results" cannot be the selection rule:
picking the write policy after seeing which one makes Arm B win is the tuning
`CLAUDE.md` forbids. `write_all` is chosen before any run, because it keeps the
error-spreading effect measurable. A confident-only policy remains the
optional third variant (A3). **Status:** answered 2026-10-13.
### C6. Does memory carry over between runs?

**Recommendation: no.** Each scored run gets its own fresh store on disk. Memory
surviving a restart is a real product property and is satisfied by this; memory
carrying across scored runs would make run 2 incomparable to run 1.

**Status:** open. OQ-7.

**Answer: no — each scored run gets its own fresh store. The explanation asked
for** (recorded 2026-10-22):

Two different things hide behind "carry over", and the answer differs for each.

- **Across a restart: yes, memory persists, and that is deliberate.** The store is
  a ChromaDB directory on disk, never in-memory (`CLAUDE.md`). Stop the system and
  start it again and nothing is lost. That is the real product property and it is
  satisfied.
- **Across a scored run: no.** Each run writes to its own directory,
  `paths.memory_store(run_id)`, created empty.

The reason for the second is that Arm B's result depends on what memory already
holds. If run 2 inherited run 1's store it would begin with 165 cases run 1 never
had, so the two would not be measuring the same system — and the three repeats
**B3** asks for could not be averaged, because each would start somewhere
different. Every run starting empty is what makes "the only difference between
the arms is memory" true.

It is also what makes **C7** coherent: an empty start is either the condition or
it is not, and pre-loading would contradict this answer.

**Status:** answered 2026-10-22. Implemented since 2026-10-13.

### C7. Is memory pre-loaded before the run starts?

**The question:** memory begins empty, so the first alerts get no benefit. Do we
pre-fill it?

**Recommendation: no.** Report the early alerts and the later alerts as two
separate figures instead — "while memory was filling" and "once it was full."
Pre-filling with the true labels would be the answer key again; pre-filling with
hand-written cases would be inserting our own beliefs into the result.

**Status:** open. OQ-4. Note the A3 decision does **not** settle this.

**Answer:** Brand new memory after every run

**Implemented 2026-10-13:** no pre-loading. Every run's store is its own
directory, `paths.memory_store(run_id)`, and starts empty. **Status:** answered
2026-10-13.

### C8. How many past alerts get retrieved, and is there a similarity cut-off?

**Recommendation: 3, and no cut-off.**

- **3, not more:** the 2nd-to-5th closest matches are worse than the closest, so a bigger number adds noise.
- **No cut-off:** right and wrong matches score virtually the same — 0.998 against 0.997 — so there is no threshold that separates good matches from bad ones. Try the sweep anyway and report that it found nothing.

~~**Status:** open. Tracked within BL-005.~~ *(superseded by the answer below.)*

**Ans**: max 3 retrievals

**Implemented 2026-10-13:** top 3, no cut-off (`store.TOP_K`). Re-measured on
all 215 clean alerts: correct and wrong nearest matches both have a median
similarity of 0.997, so a threshold still separates nothing. See Figure 3 in
`notebooks/retrieval-quality.ipynb`. **Status:** answered 2026-10-13.

### C9. Does the detector get a version identifier?

**The question:** nothing in the code or the output records which model produced
an alert.

**Recommendation: add one.** Without it, an accidental change to the detector
would be undetectable afterwards, and a stored alert cannot be traced back to the
model that produced it.

Ans: version id should be there

**Status:** answered, **not built** — still true on 2026-10-22. Tracked as BL-075.
Three complete runs now exist and no alert record carries a detector version: an
alert in `artifacts/model_outputs/live_results.jsonl` holds `uid`, addresses,
`proto_name`, `captured_at`, `status`, `binary_confidence`, `multiclass` and
`alert`, and nothing identifying the model that produced it. Each run's
`run_config.json` pins the git commit, which recovers it indirectly for those
runs only. Still quick to fix.

### C10. Do stored alerts carry a format version number?

**Recommendation: yes.** If the detector is ever retrained on the other dataset,
the attack type names change completely and every stored alert becomes invalid.
A version number makes that a clean break instead of silent corruption.

**Status:** open. Tracked as BL-006. Quick to fix.

Ans: yes this has to be there

**Implemented 2026-10-13:** `schema_version "1.0"` is on every case and on the
collection. A store written under any other version, embedding model or
condition is refused. **Status:** answered 2026-10-13. BL-006 closed.

---

# Part D — Answer before submitting the paper

### D1. What are the research questions, written out?

**Why it matters:** the review asks for them explicitly and the current draft has
none.

**Answered 2026-10-10**, re-ordered to match the **B1** decision. Question 1 is
now the headline, and it carries the objective already submitted to the mentors:

1. **Does memory reduce unnecessary escalations without missing real threats?** Measured as escalation precision together with must-escalate recall, over the 215 held-out alerts, against the tier split declared in **B1**. 94 units of headroom.
2. **Does memory improve how often the attack type is named correctly?** 51 units of headroom, and the no-memory figure is already measured.
3. **Does memory reduce repeated mistakes on alerts that look alike?** Consistency across near-duplicate alerts.
4. **What does it cost to store the LLM's own unchecked conclusions instead of confirmed ones?** *(This is what A3 sets up.)* Drop this one first if time runs short — and remove it from the paper rather than leaving it claimed and unmeasured.

A null or negative result on any of these is a valid outcome and is reported as
one. Note that the sandbox retrieval test already found nearest-neighbour
retrieval **worse than random** on exactly the alerts the detector got wrong, so a
null result on Arm B is a live possibility and the paper should be built to
survive it.

**Status 2026-10-22 — three of the four were measured; the headline one was not.**

| | Research question | Result |
|---|---|---|
| 1 | Does memory reduce unnecessary escalations without missing real threats? | **Not measured.** No `priority` field was ever added, so no run produced an escalation number. See **B1**. |
| 2 | Does memory improve how often the attack type is named correctly? | **Measured — and the answer is no, it makes it worse.** Gemma 54.5% → 23.6% (p = 5.7 × 10⁻¹²); `gpt-oss-20b` 32.7% → 18.8%. |
| 3 | Does memory reduce repeated mistakes on alerts that look alike? | **Measured — and the answer is yes, but it is the mechanism of the damage.** Gemma reached a uniform family on 17 of 17 near-duplicate groups *while* accuracy collapsed: memory makes the model agree with itself, not think harder. |
| 4 | What does it cost to store unchecked conclusions instead of confirmed ones? | **Measured, and it is the cleanest result in the project.** B-oracle — same retrieval, correct stored labels — recovers family accuracy to 69.1% on Gemma and 64.8% on `gpt-oss-20b`. The cause is the *content* of memory, not retrieval. |

The warning above held. The paper did not need to survive a null result on Arm B;
it needs to survive a **negative** one on question 2, which is a stronger finding
than a null and must be reported as measured (`CLAUDE.md`).

**Status:** answered. Tracked as BL-020.

### D2. Does the report-writing pipeline stay in the paper?

**The question:** the pipeline that writes a narrative summary over the whole
stream is unrelated to the memory question, is never evaluated, and is currently
claimed as the paper's second contribution.

**Recommendation:** cut it to a short implementation note, or evaluate it
properly (does the narrative match the statistics, and does it invent anything).
Pick one. Do not leave it claimed but unmeasured.

**Status:** open. Tracked as BL-020 and BL-008.

### D3. How is the 2026-08-30 pilot run handled?

**The question:** it cannot be reproduced — re-running two of its 40 verdicts
through an identical prompt flipped one answer outright.

**Recommendation:** do not use it as the baseline. Re-run the no-memory arm in
the same time window as the memory arm, and list model drift as a limitation.

**Status:** open, and effectively forced. Tracked as BL-009.

### D4. Is the code published, anonymised?

**Recommendation: yes**, the review asks for it directly. Check first that no
API key, no `.env` file and no dataset is included.

**Status:** open.

---

# Part E — Facts we need from outside this repository

Not judgement calls. Someone has to go and look.

### E1. What is the actual token allowance on the paid tier?

Needed to schedule the runs and to state the cost in the paper. Check
`console.groq.com/settings/limits`. Tracked as BL-011.

Ans: not using paid tier
### E2. When is the paper due?

Everything in Part B and Part C is sized against this and it is not written down
anywhere.

14th October

**That date has passed** — it is now 2026-10-22 and the last run finished on the
22nd. The real submission date is written **nowhere in this repository**, and both
Part B and Part C were sized against it. Someone has to write it down.

### E3. What are "B11", "D1" and "B6"?

`memsoc-sandbox/FINDINGS.md` says its results feed into "OQ-8, B11, D1 and B6".
OQ-8 exists in this repository. The other three do not appear anywhere. If they
are from another register, that register needs linking here.

---

---

# Part F — What was actually run, 2026-10-15 to 2026-10-22

Added 2026-10-22. Parts A to E are the questions; this is the answer the project
actually produced. **No further runs are planned** — the free tiers (**A4**) are
exhausted and the Gemma run below is the terminal result.

### The runs

| Tester | Model | Protocol | Scope | Arms | Write-up |
|---|---|---|---|---|---|
| **M** | `gemma-4-26b-a4b-it` (AI Studio) | **v3** | 165 alerts × 3 arms = **495 verdicts** | A, B-self, B-oracle | [`status/gemma-p3-results.md`](./status/gemma-p3-results.md) |
| **G** | `openai/gpt-oss-20b` (Groq) | v1 | 165 alerts × 3 arms = 495 verdicts | A, B-self, B-oracle | [`status/groq-gptoss20b-p1-results.md`](./status/groq-gptoss20b-p1-results.md) |
| **Q** | `qwen/qwen3.8-27b` (Groq) | not recorded in the write-up; output cap 1,000 (BL-134) | 250 alerts × 2 arms = 500 verdicts | A, B-self only | [`status/qwen-results.md`](./status/qwen-results.md) |

All on the first alerts in stream order, temperature 0, prompt variant
`label-hypothesis-v1`, embedding `all-MiniLM-L6-v2` at commit `1110a243`, top-3,
no cut-off, write-all. **The three are never pooled** — different models, and in
G's case a different protocol version. The Gemma run is the one to quote: it is
the only one on protocol v3, and `protocol_run --verify` passes **17 of 17**
checks on it, including "Arm A retrieved nothing" and "retrieval matches the
reference machine (0 of 165 alerts differ)".

### What they answered

**1. Self-memory cut missed attacks roughly in half — on one model.** Gemma: 42
missed attacks down to 22 of 165, recall 0.745 → 0.867, McNemar
**p = 1.1 × 10⁻⁵**. This is the project's defensible positive finding.

**2. And it wrecked the labels.** Gemma family accuracy 54.5% → 23.6%,
**p = 5.7 × 10⁻¹²**, 56 broken against 5 fixed. The frozen detector names
families correctly 82.4% of the time, so **no arm beat the detector** at that job
— the best, B-oracle, reaches 69.1%.

**3. The cause is isolated, and it is unchecked memory rather than memory.**
B-oracle — identical retrieval, correct stored labels — recovers to 69.1%. Error
propagation through self-memory is the failure mode `PROJECT_BRIEF.md` §8 names
as the most important one: it was predicted, then measured, then causally
separated from retrieval. Per `CLAUDE.md` it must not be tuned away.

**4. The effect is model-dependent, which is itself a finding.** On
`gpt-oss-20b`, self-memory hurt *both* halves — recall 40.2% → 26.1%, category
32.7% → 18.8% — the opposite shape to Gemma's. On Qwen the model sat at the floor
(Arm A caught 5 of 250, B-self 0) and the run cannot answer the question at all.
One model improving on recall is not "memory helps".

### What they did not answer, and why

| Gap | Why | Tracked |
|---|---|---|
| **The declared headline metric** — unnecessary-escalation rate | the `priority` field was never approved or added | **B1**, BL-105, BL-106 |
| Run-to-run variation on Arm B | one run per arm, not three; free-tier quota | **B3**, BL-017 |
| Whether the baseline prompt is the strongest of the three | the comparison in **B4** was never run | **B4**, BL-018 |
| The LLM's own false-positive rate | no benign flow was ever sent to it | **B2**, BL-016 |
| Whether the result holds beyond 165 alerts | 165 of 1,135 alerts were triaged | BL-118 |

Each belongs in the paper's limitations section as written, not softened. Two of
them — the first and the third — are places where this file declared an intention
and the project then did not carry it out, so they are answered better by saying
so than by hoping nobody checks.

---

## Where the detail lives

| For | Read |
|---|---|
| Full reasoning and rejected options on C1–C8 | [`memory-layer/07-open-questions.md`](./memory-layer/07-open-questions.md) |
| Every open bug, gap and piece of debt, with IDs | [`PRODUCT_BACKLOG.md`](./PRODUCT_BACKLOG.md) |
| The mentor's review in full | `research-paper/Review - MemSOC -30092026.docx` |
| Why false alarms have nothing to improve | [`llm-triage/MISSING_PER_ALERT_VERDICTS_AND_FP_HEADROOM.md`](./llm-triage/MISSING_PER_ALERT_VERDICTS_AND_FP_HEADROOM.md) |
| The terminal result, in full | [`status/gemma-p3-results.md`](./status/gemma-p3-results.md) |
| The other two model runs | [`status/groq-gptoss20b-p1-results.md`](./status/groq-gptoss20b-p1-results.md), [`status/qwen-results.md`](./status/qwen-results.md) |
| How a run is executed and verified | [`status/testing-protocol-v3.md`](./status/testing-protocol-v3.md) |
| The sandbox measurements in full | `../../memsoc-sandbox/FINDINGS.md` |
| What the project is and what must not change | [`../PROJECT_BRIEF.md`](../PROJECT_BRIEF.md), [`../CLAUDE.md`](../CLAUDE.md) |

This file is the short version and the place to record answers. Where it
disagrees with an older document, this file is newer — fix the older one.
