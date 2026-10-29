# Protocol v4: pre-registration note

> **Committed 2026-10-29, before any v4 run.** The v4 runner refuses every real run until this exact file is
> committed **and** the checkout is the `memsoc-protocol-v4` tag (`src/memsoc/triage/protocol_v4.py`).
> The items in §7 were still open at commit time. Each is settled by a dated addendum in §8 **before the tag
> is created**. Nothing above §8 is edited after this commit.
>
> **Owner:** Person 3. **Plan:** [`protocol-v4-execution-plan.md`](../work-split/protocol-v4-execution-plan.md).
> **Approved scope:** [`protocol-v4-time-estimate.md`](../work-split/protocol-v4-time-estimate.md), "What was approved".

---

## 1. What this note is for

It fixes, **before any v4 result exists**, what each experiment tests, which numbers will be compared, and
what result would count for or against each idea. Git's timestamp on the commit is the proof that these
were set before the results were seen.

The frozen Gemma p3 results ([`gemma-p3-results.md`](./gemma-p3-results.md)) remain the main experiment.
Everything below is **supplementary, protocol v4**, and is reported as such.

## 2. What stays fixed

Every v4 run uses the same setup as p3. Nothing here is tuned per experiment.

| Held fixed | Value |
|---|---|
| Model | `gemma-4-26b-a4b-it`, temperature 0, output cap 16,384 |
| Alerts | the same 165 p3 alerts (all real attacks), in the p3 order unless an experiment says otherwise |
| Detector | frozen; same weights and thresholds |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` at revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` |
| Retrieval | top 3, no similarity cutoff, earlier alerts only |
| Prompt | the p3 template; Arm A's prompt stays byte-identical (the only possible change is BL-170, §3.2) |
| Data | `generated_logs.jsonl`, `ground_truth.csv`, `live_results.jsonl` with the SHA-256 values in the p3 `run_config.json` |
| Scoring | the unchanged `memsoc.triage.score_verdicts` |

## 3. The experiments

Each memory experiment is one setting of the memory module, run through the same code as p3. None is a
separate triage path.

### 3.1 Shuffled-label memory (Person 1), `bshuf-gemma4-26b-p4`

**What changes:** the same 3 retrieved cases as true-label memory (B-oracle), but each case's label is
replaced by a true label drawn at random from all cases stored so far. The draw is seeded from the alert's
id, and every replacement is logged in `shuffles.jsonl`.

**What it tests:** does B-oracle do better because its labels are *correct*, or just because it has *some*
labels?

**Note:** all 165 alerts are attacks, so every stored verdict is "attack". Only the **attack family** is
shuffled; the verdict shown never changes (BL-172). A random draw can also land on the right family by
chance. Both points will be stated with the result.

### 3.2 Label-free memory (Person 3), `bnolabel-gemma4-26b-p4`

**What changes:** B-self with the attack family removed. Stored cases keep the alert text, the model's own
attack/false-alarm verdict and its confidence. The precedent block shows only those. The answer format is
unchanged, so family accuracy can still be scored.

**What it tests:** in p3, B-self caught more attacks but named families much worse. Does dropping the
family keep the first effect and remove the second?

**Depends on:** BL-170. The precedent block is drawn in `triage_prompt.py`, a protected file. Removing the
family there needs explicit approval. **This experiment does not run without it.**

### 3.3 Reversed order (Person 3), `bself-rev-gemma4-26b-p4`

**What changes:** B-self on the exact reverse of the 165-alert order, from a new, empty store. The SHA-256
of the reversed order is recorded in `run_config.json`.

**What it tests:** the p3 order starts with Fuzzers, and B-self then labelled all 143 of its escalations
Fuzzers. Is that the effect of memory, or of which alert happened to come first?

Arm A judges each alert alone, so its p3 results are reused rather than rerun.

### 3.4 Hard-benign, attack-primed stream (Person 2), `armA-benign-…` and `bself-benign-gemma4-26b-p4`

**What changes:** 100 harmless flows, the ones the detector scored highest, taken only from rows the
detector never trained on, with near-duplicates removed. B-self starts from a copy of its memory at the end
of the p3 run (165 cases; `chroma.sqlite3` SHA-256
`fd5ba38c3143d7918d4685aba762b1b1fccee070c0ea4386b3ebe67c1de31d55`) and keeps writing back. Arm A sees the
same 100 flows.

**What it tests:** p3 had no harmless traffic, so "always escalate" scored perfectly and fewer false alarms
could not be measured. Does a memory full of attacks make the model call harmless traffic an attack?

**The selection rule** (ranking, seed, near-duplicate method) is **open at commit time** (§7) and is fixed
by a §8 addendum from Person 2. The hash of the final list is committed before any benign run.

### 3.5 Nearest-neighbour baseline (Person 3), no LLM

A 3-neighbour vote over true labels, using the retrieval the p3 runs actually logged, on the same 165
alerts. It needs no new run and is computed by `python -m memsoc.triage.knn_baseline`.

**Disclosure:** it was computed before this note was written (2026-10-29), from data that already existed.
It is a reference row, not a test of a hypothesis below.

## 4. What is measured

All from `score_verdicts`, as in p3.

| Measure | Used for | Definition |
|---|---|---|
| **Recall** | 3.1–3.3 | attacks marked "attack", out of all attacks |
| **Family accuracy** | 3.1–3.3, 3.5 | alerts whose attack family matches ground truth |
| **False-escalation rate** | 3.4 (main measure) | harmless flows marked "attack", out of the 100 **[to confirm: §7]** |
| **Inconclusive count** | all | reported on its own, never counted as correct |

**Comparisons** are paired, alert by alert, with the exact two-sided McNemar test
(`score_verdicts.paired_mcnemar`). The counts of alerts fixed and broken are always reported beside p.
Wilson 95% intervals are given for every rate. The first 10 alerts and the rest are also reported
separately (`cold_start_split`), as in p3.

## 5. Hypotheses, and what would support or contradict each

"Significant" means p < 0.05 on the paired test above. A result that is not significant is reported as
"no detectable difference", not as "no difference".

| # | Idea | Supported if | Contradicted if |
|---|---|---|---|
| **H1** | B-oracle names families better because its labels are correct | shuffled-label family accuracy is significantly **below** B-oracle's (p3: 69.1%) | shuffled-label is not significantly below B-oracle |
| **H2a** | Label-free memory keeps the recall gain | label-free recall is significantly **above** Arm A's (p3: 74.5%) | label-free recall is not significantly above Arm A |
| **H2b** | Label-free memory removes the family harm | label-free family accuracy is significantly **above** B-self's (p3: 23.6%) | label-free is not significantly above B-self |
| **H3** | The p3 B-self result is not just the alert order | reversed B-self has significantly higher recall **and** significantly lower family accuracy than Arm A, as p3 did | either difference is missing or reversed |
| **H4** | A memory of attacks makes harmless traffic look like attacks | B-self's false-escalation rate on the 100 flows is significantly **above** Arm A's | it is not significantly above Arm A |

What each outcome would mean:

- **H1 contradicted:** the gain from true-label memory does not depend on the label being right.
- **H2a and H2b both supported:** the harm in p3 came from the stored family, and storing only the verdict
  avoids it.
- **H3 contradicted:** the p3 B-self result may depend on the order, and the paper must say so.
- **H4 supported:** memory's recall gain comes at the cost of more false alarms.

## 6. Commitments

1. **Every result is reported,** whether or not it supports a hypothesis, including runs that fail or stop.
2. **No tuning after the fact.** No prompt, threshold, seed, retrieval setting or metric changes once a
   result has been seen.
3. **No reruns to get a better number.** A run is resumed after an interruption, never restarted to replace
   its results. If a run has to start again from scratch, both attempts and the reason are reported.
4. **p3 stays untouched.** `artifacts/shared/memsoc-p3-gemma4-26b-results/` is never written to.
5. **Labelled supplementary.** Every v4 number is labelled "supplementary, protocol v4" wherever it appears.

## 7. Open at commit time (settled in §8 before the v4 tag)

Each answer goes into §8 as a dated addendum. No v4 result exists until the tag does, so every answer is
still fixed before any result is seen.

| Item | Owner | Backlog |
|---|---|---|
| Approval for the label-free edit to `triage_prompt.py`. Without it, drop §3.2, H2a and H2b | Supervisor | BL-170 |
| Confirm that a family-only shuffle is the intended test | Supervisor | BL-172 |
| The benign selection rule: ranking, seed, near-duplicate method (§3.4) | Person 2 | — |
| Confirm the false-escalation rate's denominator: all 100 flows, or only those given a verdict | Team | BL-177 |
| Decide whether to correct for multiple tests (five hypotheses; for example Holm), or report each p as it is | Team | BL-177 |

## 8. Addenda

Dated, in order, each one settling a §7 item. None yet.
