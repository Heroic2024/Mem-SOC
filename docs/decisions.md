# Decisions — the file that steers this project

Every question this project still has to answer, in the order it has to be
answered. Four are already answered; those come first so nobody re-opens them.

**How to use this file.** Find the question. Read the recommendation. Decide.
Then write the answer and the date into this file. A decision made in a
conversation and not written here is not a decision.

**Last updated:** 2026-10-02

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

All measured, not estimated. All from the current stream, which has the problem
described in **A1** below.

- The detector flagged **211** flows out of 5,000. Of those, **210 were real attacks, 1 was a false alarm, and it missed nothing.**
- It named the attack type correctly for **187 of 211**. So **24 were the wrong type.**
- **82% of that stream was data the detector had already been trained on** — including 173 of the 211 alerts. The three figures above are therefore flattering.
- **470,122** rows of the dataset were never used for training and are untouched.
- Pilot run of 40 alerts, 2026-08-30: the LLM agreed with the true labels on **12**, and called **28 real attacks harmless.** That run cannot be reproduced.
- Sandbox test on the 211 alerts: the most similar past alert had the right attack type **64%** of the time. Random guessing gets 29%. The detector gets 89%. **On the 24 the detector got wrong, it was 21% — no better than guessing.**
- The draft description format for a stored alert was **too long for the embedding model**: 179 of 211 were silently cut short. A shorter format of the same information fits with room to spare.

---

## Do these three things next

1. Back up `artifacts/generated_logs.jsonl`, `artifacts/ground_truth.csv` and `artifacts/model_outputs/live_results.jsonl`. They are a matched set and the generator overwrites them without warning.
2. Rebuild the stream from the 470,122 untrained-on rows, re-run the detector, and re-measure the three figures above. **This costs nothing** — no LLM calls.
3. Answer **B1** using those new numbers. Everything else in Part B follows from it.

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

Tracked as BL-025. Blocked by BL-022 (the generator destroys its own output
files on each run).

### A2. Do we build the memory layer and run the comparison, or write up the baseline only?

**Answer: build it and run the comparison, cut to the minimum that holds up.**

The mentor's review says a paper that asks whether memory helps and then only
reports the no-memory arm would be rejected. So the comparison has to happen.

Minimum scope: one LLM, one prompt version, 3 repeat runs per arm. Dropped for
now: a second LLM, few-shot prompting comparison.

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

### A4. Free API tier or paid?

**Answer: paid.**

The free tier allows roughly 40 alerts per day in total. The runs this project
needs are in the low thousands of calls. Paying removes the constraint for a
small amount of money and does **not** change which model is used, so nothing
about the experiment changes.

---

# Part B — Answer before spending any money on LLM runs

Changing any of these after a run starts throws that run away. They are the
urgent ones.

### B1. Which single number is the headline result?

**The question:** is the main result "memory reduces false alarms" or "memory
names the attack type correctly more often"?

**Why it matters:** false alarms are what the project brief names as the main
measure, but there is exactly **one** false alarm in 211 alerts — so there is
almost nothing for memory to improve. Attack-type accuracy has 24 wrong answers,
so there is something to improve.

**Recommendation:** decide this **after** step 2 in *Do these three things next*.
On untrained-on data the detector will make more mistakes of both kinds, and the
original measure may become usable again. Deciding before that measurement means
guessing.

**Status:** blocked on a free measurement. Tracked as BL-012.

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

**Status:** open. Tracked as BL-016.

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

**Status:** open. Tracked as BL-017, and settles half of OQ-6.

### B4. Which version of the prompt do we use?

**The question:** three options — tell the LLM the detector's answer is correct;
hide the detector's answer; or show it as a guess to check (what we do now).

**Why it matters:** showing it as a guess may be the reason the LLM called 28 of
40 real attacks harmless. If the baseline is needlessly weak, any improvement
from memory looks bigger than it is.

**Recommendation:** test all three on the no-memory arm, pick the strongest, then
freeze it and use the same one in both arms. Making the baseline *stronger* works
against memory, so this is the safe direction to tune in.

**Status:** open. Tracked as BL-018.

### B5. Which exact LLM, at which setting?

**The question:** the full model name and version, and the temperature.

**Why it matters:** the review lists these as missing from the paper. Separately,
re-running two pilot verdicts through an identical prompt **changed one answer
and moved the other's confidence**, so the hosted model drifts over time. The
exact identifier and the dates of the runs have to be recorded.

**Recommendation:** temperature 0, one named model and version, both arms run in
the same time window, and model drift listed as a limitation.

**Status:** open. Related to BL-009.

---

# Part C — Answer before building the memory layer

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

**Status:** open. OQ-1.

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

### C4. Where does the stored attack type come from?

**Recommendation:** the LLM's own answer, kept as a separate field from the
detector's answer. Where the two disagree is itself a result worth reporting.

**Status:** open. OQ-3.

### C5. Which alerts get written to memory — all of them, or only confident ones?

**Recommendation: all of them**, for the main result. Filtering out the uncertain
ones hides the error-spreading effect the brief requires us to measure, and it
removes exactly the hard cases where memory might help.

For reference: filtering at a detector confidence of 0.75 would keep 114 of 211
alerts and exclude 20 of the detector's 24 mistakes — tidier memory, but the hard
cases are gone. Do not pick that number off this page; it was measured against
the answer key.

**Status:** open. OQ-5.

### C6. Does memory carry over between runs?

**Recommendation: no.** Each scored run gets its own fresh store on disk. Memory
surviving a restart is a real product property and is satisfied by this; memory
carrying across scored runs would make run 2 incomparable to run 1.

**Status:** open. OQ-7.

### C7. Is memory pre-loaded before the run starts?

**The question:** memory begins empty, so the first alerts get no benefit. Do we
pre-fill it?

**Recommendation: no.** Report the early alerts and the later alerts as two
separate figures instead — "while memory was filling" and "once it was full."
Pre-filling with the true labels would be the answer key again; pre-filling with
hand-written cases would be inserting our own beliefs into the result.

**Status:** open. OQ-4. Note the A3 decision does **not** settle this.

### C8. How many past alerts get retrieved, and is there a similarity cut-off?

**Recommendation: 3, and no cut-off.**

- **3, not more:** the 2nd-to-5th closest matches are worse than the closest, so a bigger number adds noise.
- **No cut-off:** right and wrong matches score virtually the same — 0.998 against 0.997 — so there is no threshold that separates good matches from bad ones. Try the sweep anyway and report that it found nothing.

**Status:** open. Tracked within BL-005.

### C9. Does the detector get a version identifier?

**The question:** nothing in the code or the output records which model produced
an alert.

**Recommendation: add one.** Without it, an accidental change to the detector
would be undetectable afterwards, and a stored alert cannot be traced back to the
model that produced it.

**Status:** open. Tracked as BL-075. Quick to fix.

### C10. Do stored alerts carry a format version number?

**Recommendation: yes.** If the detector is ever retrained on the other dataset,
the attack type names change completely and every stored alert becomes invalid.
A version number makes that a clean break instead of silent corruption.

**Status:** open. Tracked as BL-006. Quick to fix.

---

# Part D — Answer before submitting the paper

### D1. What are the research questions, written out?

**Why it matters:** the review asks for them explicitly and the current draft has
none.

**Recommendation**, taken from the review:
1. Does memory improve how often the attack type is named correctly?
2. Does it reduce repeated mistakes on alerts that look alike?
3. What does it cost to store the LLM's own unchecked conclusions instead of confirmed ones? *(This is what A3 sets up.)*

**Status:** open. Tracked as BL-020.

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

### E2. When is the paper due?

Everything in Part B and Part C is sized against this and it is not written down
anywhere.

### E3. What are "B11", "D1" and "B6"?

`memsoc-sandbox/FINDINGS.md` says its results feed into "OQ-8, B11, D1 and B6".
OQ-8 exists in this repository. The other three do not appear anywhere. If they
are from another register, that register needs linking here.

---

## Where the detail lives

| For | Read |
|---|---|
| Full reasoning and rejected options on C1–C8 | [`memory-layer/07-open-questions.md`](./memory-layer/07-open-questions.md) |
| Every open bug, gap and piece of debt, with IDs | [`PRODUCT_BACKLOG.md`](./PRODUCT_BACKLOG.md) |
| The mentor's review in full | `research-paper/Review - MemSOC -30092026.docx` |
| Why false alarms have nothing to improve | [`llm-triage/MISSING_PER_ALERT_VERDICTS_AND_FP_HEADROOM.md`](./llm-triage/MISSING_PER_ALERT_VERDICTS_AND_FP_HEADROOM.md) |
| The sandbox measurements in full | `../../memsoc-sandbox/FINDINGS.md` |
| What the project is and what must not change | [`../PROJECT_BRIEF.md`](../PROJECT_BRIEF.md), [`../CLAUDE.md`](../CLAUDE.md) |

This file is the short version and the place to record answers. Where it
disagrees with an older document, this file is newer — fix the older one.
