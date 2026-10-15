# Arm A Baseline Run — LLM Triage Without Memory

> First scored run of the Phase 1 memoryless baseline (Arm A), against the NF-UNSW-NB15-v3 stream.
> Build details and the decisions behind this pipeline are in
> [`MISSING_PER_ALERT_VERDICTS_AND_FP_HEADROOM.md`](./MISSING_PER_ALERT_VERDICTS_AND_FP_HEADROOM.md).
>
> **Run date:** 2026-08-30 · **Model:** `openai/gpt-oss-20b` (Groq), temperature 0 · **Arm:** baseline, no memory

---

## Run parameters

| | |
|---|---|
| Flows in stream | 5,000 (4,653 captured and joinable) |
| Alerts raised by detector | 194 (4.32% of flows) |
| Stratified sample defined | 75 alerts, capped at 12 per detector category, seed 20260830 |
| **Verdicts actually scored** | **40** — run stopped early on wall-clock cost |
| Requests consumed | 40 |
| Mean latency | 2,654 ms per alert |

**The run is incomplete.** It was halted because throughput on the Groq free tier is roughly one alert per
minute (see [Why it was so slow](#why-it-was-so-slow)), making a full arm a multi-hour job. The 40 verdicts
were taken in stream order rather than sampled randomly, so they over-represent early alerts and the
`Exploits` category. Treat the numbers as directional, not final.

The effect sizes below are large enough that sampling is unlikely to explain them — but they should be
re-measured on a complete arm before being quoted anywhere.

---

## Scorer output

```
==============================================================
  Phase 1 scoring -- arm: baseline -- 40 alerts scored
==============================================================

1. VERDICT vs GROUND TRUTH  (the experiment)
   escalate = true_positive, dismiss = false_positive

   TP   12   correctly escalated a real attack
   FP    0   escalated benign traffic  <-- false-positive volume
   FN   28   dismissed a real attack   <-- most costly error
   TN    0   correctly dismissed a false alarm
   inconclusive 0  (excluded from the rates below)

   precision 1.000   recall 0.300   F1 0.462   over 40 decisive verdicts

2. CATEGORY vs GROUND TRUTH  (Option A primary metric)

   LLM category accuracy      0.200
   detector, same alerts      0.825
   difference                 -0.625  (worse than the detector)
   pre-run detector baseline  0.881

   category errors (expected -> LLM said):
     Exploits         -> none             14
     DoS              -> none             5
     Fuzzers          -> none             3
     Reconnaissance   -> none             3
     Generic          -> none             2
     Exploits         -> Reconnaissance   2
     Exploits         -> Fuzzers          1
     Backdoor         -> none             1
     Exploits         -> Analysis         1

3. CATEGORY vs DETECTOR  (echo check -- NOT a correctness measure)

   agreement with detector    0.300

   NOTE: the LLM overrules the detector on more than half of alerts.
   Check section 2 -- if accuracy did not improve, it is disagreeing
   without being more right, which is worse than echoing.

4. CONSISTENCY across near-duplicate alerts
   grouped by (detector_label, dst_port, protocol), groups of 2+

   groups                     8
   uniform verdict            7 (87.5%)
   uniform category           7 (87.5%)

5. COST

   mean latency  2654 ms
   LLM requests  40
```

---

## Explanation of what happened

### The headline: the LLM is much worse than the detector it is reviewing

| Measure | LLM | Detector, same 40 alerts |
|---|---|---|
| Category accuracy | **0.200** | 0.825 |
| Recall | **0.300** | 1.000 |
| Real attacks missed | **28 of 40** | 0 |

**Ignore the precision of 1.000.** It looks perfect only because the alert set contains almost no benign
traffic to wrongly escalate — the detector produces just one false positive in the entire 5,000-flow stream.
Precision here is an artifact of the data, not a result. `F1 0.462` is likewise flattered by it; recall is the
number that matters.

### The failure is one behaviour, repeated

The category errors are not confusion *between* attack families. **29 of the 32 errors are `X → none`** — the
LLM declaring real attack traffic to be benign. Fourteen Exploits, five DoS, three Fuzzers, three
Reconnaissance, one Backdoor, all dismissed as ordinary.

It does this **confidently**: mean confidence on the 28 missed attacks is **0.82**. This is not a model
hedging under uncertainty; it is a model that believes it is right.

Three verbatim rationales from missed `Exploits`:

> *"FTP session on port 21, only 13/11 packets, 705/886 bytes, low throughput, normal PSH/ACK flags, 150
> response code. No large payload or anomalous IAT. Flow looks like a benign FTP data transfer, not an
> exploit."* — confidence 0.92

> *"HTTP on port 80, 10 in/8 out packets, 786/1104 bytes, typical GET/response sizes, normal TTL 62-63, flags
> consistent with a normal TCP handshake/FIN. No payload anomalies; detector likely misattributed TTL and flag
> patterns."* — confidence 0.90

> *"Port 80 ... typical HTTP GET/response ... but overall flow matches benign HTTP. Flags odd but likely
> misinterpreted."* — confidence 0.85

### Why this happens

Each rationale is, on its own terms, **sound analytical reasoning**. A small HTTP exchange with a normal
handshake, unremarkable packet sizes and ordinary timing genuinely does look like ordinary traffic.

The problem is that NF-UNSW-NB15-v3 attack flows *do not look anomalous at NetFlow level*. The detector is not
reading human-legible attack signatures — it is a gradient-boosted tree picking up subtle statistical
regularities across 48 numeric features, quite possibly including artifacts of how the testbed capture was
generated. Those regularities are not the kind of evidence an analyst reasons from, and they are not
recoverable by reading the flow record in natural language.

Note the third rationale explicitly reasoning *against* the evidence — "flags odd but likely misinterpreted."
The model saw the anomaly and explained it away.

**This is a finding in its own right, independent of the memory question:** an LLM given full NetFlow
measurements cannot reproduce a trained classifier's judgement on this dataset, and fails in a confident,
one-directional way rather than by hedging.

### The agreement rate rules out the failure mode we were guarding against

Agreement with the detector is **0.300**, so the LLM is clearly not echoing the detector's label — the risk
that the locked prompt was written to avoid. But section 3's warning applies: it is disagreeing **without
being more right**, which is the worse of the two failure modes. Independent reasoning that is wrong is less
useful than copying something that is right.

### Consistency is high, but do not read it as a positive

87.5% of near-duplicate groups received a uniform verdict. That sounds encouraging until you notice *what*
it is being consistent about: it is reliably calling similar attack flows benign. **Consistency measures
stability, not correctness**, and a systematically biased model scores well on it. This metric will only
become informative once accuracy is non-trivial.

---

## What this means for the experiment

### The headroom problem is solved — on a different axis

[`MISSING_PER_ALERT_VERDICTS_AND_FP_HEADROOM.md`](./MISSING_PER_ALERT_VERDICTS_AND_FP_HEADROOM.md) flagged
that false-positive volume had **one** correctable unit, making the original primary metric unmeasurable.

That concern is resolved. Arm A leaves **28 false negatives in 40 alerts** to correct. There is abundant room
for a memory layer to demonstrate value, and the mechanism maps directly onto the project's thesis: the LLM
cannot judge these flows from first principles, but *"flows measuring like this one were previously confirmed
Exploits"* is exactly the precedent that would fix it.

The metric that moves is **recall / false-negative volume**, not false-positive volume. That should be
recorded against the Option A decision in
[`memory-layer/07-open-questions.md`](./memory-layer/07-open-questions.md).

### But error propagation is now the expected outcome, not a risk ⚠️

This is the most important consequence and it needs a decision before Arm B is built.

Under the current working assumptions — [OQ-2](./memory-layer/07-open-questions.md#oq-2--does-ground-truth-feed-the-memory-store)
option (a), memory stores the LLM's *own* verdicts, plus
[OQ-5](./memory-layer/07-open-questions.md#oq-5--what-is-the-phase-2-default-write-policy)'s `write_all`
default — Arm B's memory store fills with high-confidence *"this was benign"* cases for traffic that was
actually malicious.

Retrieval then hands each new alert precedent asserting that similar flows were benign, and the LLM's existing
bias is confirmed rather than challenged. **Arm B may well score worse than Arm A**, for a reason that says
nothing about whether memory is a good idea.

Two consequences:

1. **§8's error-propagation analysis is no longer a supplementary experiment.** It is the central dynamic of
   this study, and the conditions for it now exist naturally — no mis-stored case needs to be injected.
2. **OQ-2 becomes urgent rather than open-ended.** Pure LLM-verdict memory starting from a baseline this
   biased has little opportunity to help. The hybrid option (c) — occasional confirmed verdicts modelling
   senior-analyst review — deserves reconsideration, though it must still be reported separately from the
   headline result.

### Why it was so slow

Throughput is capped by Groq's free tier at **8,000 tokens per minute**, and `gpt-oss-20b` is a reasoning
model that spends up to 6,000 completion tokens thinking before answering. Prompt plus reservation is roughly
7,200 tokens, so the quota permits about **one alert per minute** regardless of how the code is written. A
full 194-alert arm is therefore a ~3 hour job, and both arms ~6 hours.

Request count was never the constraint: 40 verdicts cost 40 requests against a 1,000/day allowance.

Options, in rough order of cost-effectiveness:

| Option | Effect | Cost |
|---|---|---|
| Paid Groq tier | Removes the token ceiling outright | Money; changes nothing experimentally |
| `reasoning_effort: low` | ~5× faster, predictable token use | Changes how hard the model thinks — previously rejected on those grounds, but that concern weighs less now the baseline is this poor |
| Non-reasoning model | Much faster | Changes a fixed component (§3); invalidates these 40 verdicts |
| Smaller sample (~40/arm) | Already demonstrated sufficient | Too thin for per-category breakdowns |

---

## Status and caveats

- **40 of 75 sampled alerts scored**, taken in stream order rather than randomly. Over-represents early alerts
  and `Exploits`. Directionally clear — 0.200 versus 0.825 is not sampling noise — but not final numbers.
- **All 40 verdicts came from the locked prompt** and remain valid; the run resumes without re-spending
  requests. Verdicts from two earlier prompt revisions were archived out rather than mixed in.
- **The prompt cannot be revised from here.** These verdicts have now been compared against ground truth, so
  any prompt change made in response would be fitting the prompt to the oracle
  ([`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §5). A poor baseline is a result to report, not a bug to tune
  away.
- `model_outputs/sample_manifest.json` pins the 75 chosen `uid`s. **Arm B must reuse it, not re-sample.**
- Sample size is a documented deviation from §3's "identical alert sequence" — still a valid controlled
  comparison provided both arms receive the same 75 alerts, but it belongs in the limitations section.

---

## Open decisions raised by this run

1. **Record that the measurable metric is recall / false-negative volume**, not false-positive volume, against
   the Option A decision.
2. **Settle OQ-2 before building Arm B.** The baseline's bias makes pure LLM-verdict memory a likely
   error-amplifier.
3. **Choose a throughput option** above, before committing to a full two-arm run.
4. **Decide whether the detector's predicted category should appear in the prompt at all.** It currently does,
   as a hypothesis. Removing it would eliminate echo risk entirely and test the LLM's independent judgement —
   a cleaner design, but a different experiment that would invalidate these 40 verdicts.
