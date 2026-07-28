# 07 — Open Questions

> [`CLAUDE.md`](../../CLAUDE.md) §173: *"Surface open questions rather than silently resolving them. Where this document is ambiguous — particularly §5 — say so and ask."*
>
> Each question below has a recommendation, but **none is decided.** Every one changes what Phase 2 builds. Record the decision and its rationale in this file when made; a decision that lives only in a conversation is not a decision.

| ID | Question | Blocks | Recommendation |
|---|---|---|---|
| [OQ-1](#oq-1--does-the-embedded-text-include-the-verdict) | Does the embedded text include the verdict? | Phase 0 schema lock | Alert-only (symmetric) |
| [OQ-2](#oq-2--does-ground-truth-feed-the-memory-store) | Does ground truth feed the memory store? | Phase 2 write path | No — oracle only |
| [OQ-3](#oq-3--where-does-attack_category-come-from) | Where does `attack_category` come from? | Phase 0 schema lock | LLM output |
| [OQ-4](#oq-4--where-does-a-cold-start-seed-set-come-from) | Where does a cold-start seed set come from? | Phase 3 | No seed; report phases separately |
| [OQ-5](#oq-5--what-is-the-phase-2-default-write-policy) | Phase 2 default write policy? | Phase 2 | `write_all` |
| [OQ-6](#oq-6--how-many-arm-b-runs-and-how-are-they-aggregated) | How many Arm B runs, aggregated how? | Phase 4 | ≥3 seeds, report spread |
| [OQ-7](#oq-7--does-arm-b-retrieve-across-runs) | Does memory persist across runs? | Phase 2 | No — run-scoped |

---

## OQ-1 — Does the embedded text include the verdict?

**Status: open. Blocks the Phase 0 schema lock.**

### The inconsistency

[`CLAUDE.md`](../../CLAUDE.md) contains two statements that cannot both be implemented:

> §66 (write path): *"embed the case (alert features + context + verdict + rationale)"*
>
> §67 (read path): *"embed the incoming alert with the same embedding model"*

An incoming alert has no verdict — it has not been triaged yet. So the write path would embed text containing verdict and rationale, and the read path would embed text without them. Same model, structurally different text. The "same embedding model" requirement in §68 is satisfied, but its *purpose* — comparable vectors — is not.

### Options

**(a) Alert-only text — symmetric.** The embedded document describes the alert. Verdict and rationale are metadata, retrieved with the case and injected into the prompt, but not part of what determines the match.

- Query and document are identically shaped. Similarity measures "does this alert look like that alert," which is the intended semantics.
- Verdict and rationale are still fully available to the LLM — they just do not steer retrieval.
- Cost: cases with identical flow characteristics but different verdicts are equally retrievable. Arguably correct — the LLM should see both and reason about the disagreement.

**(b) Full case text — asymmetric.** Embed alert + verdict + rationale on write; alert only on query.

- Matches §66 literally.
- Degrades similarity by an amount nobody has measured. Rationale text is natural language and will dominate a vector otherwise built from numeric strings, so retrieval drifts toward *rationale-similarity* rather than alert-similarity.
- Query vectors and document vectors occupy systematically different regions.

**(c) Full case text with a query-side placeholder.** Render the query with `VERDICT: pending / RATIONALE: unknown` to restore structural symmetry.

- Preserves §66's intent while keeping the shapes aligned.
- The placeholder tokens are themselves a systematic difference, and the rationale-dominance problem in (b) remains.

### Recommendation

**(a).** It gives the retrieval semantics the system actually wants, keeps the paths genuinely symmetric, and loses nothing — verdict and rationale reach the LLM via metadata regardless. [02 — Case schema](./02-case-schema.md) is written against (a) and would need revision for (b) or (c).

**Needed from the team:** a decision, recorded here. If (b) or (c), also decide whether the rationale is truncated before embedding, since a 500-character rationale alone would consume most of the 256-token budget ([R5](./06-risks-and-limitations.md#r5--silent-truncation-at-the-token-limit)).

---

## OQ-2 — Does ground truth feed the memory store?

**Status: open. The most consequential question here.** [`CLAUDE.md`](../../CLAUDE.md) §87 explicitly asks for this decision and instructs that it not be silently made.

### The tension

§85 establishes the working assumption: ground-truth labels are the **evaluation oracle only** — the detector produces alerts, the LLM produces verdicts, ground truth scores those verdicts afterwards.

§87 then names the hazard: if ground-truth labels *also* feed the memory store as confirmed verdicts, memory becomes an oracle rather than a realistic analyst record, and results inflate.

### Options

**(a) Oracle only — no ground truth in memory.** Memory stores what the LLM concluded, right or wrong.

- Realistic: it models a SOC where analysts record their own judgments, including mistakes.
- Preserves the validity of the comparison — Arm B's advantage comes from memory, not from labels.
- **Makes error propagation ([R1](./06-risks-and-limitations.md#r1--error-propagation)) possible, which is required** — [`CLAUDE.md`](../../CLAUDE.md) §133 mandates testing it, and it cannot occur if stored verdicts are always correct.

**(b) Ground truth as confirmed verdicts in memory.** Store the true label rather than the LLM's verdict.

- Memory becomes a lookup table of correct answers. Retrieval of a similar past case effectively hands the LLM the label.
- Arm B would very likely win, and the result would measure **label leakage, not memory.**
- Error propagation becomes untestable by construction.
- **This invalidates the experiment as a memory study.**

**(c) Hybrid — LLM verdicts by default, ground truth on a small "reviewed" subset.** Models a SOC with periodic senior-analyst review.

- Realistic in spirit, and an interesting variant.
- Introduces a new parameter (review rate) that must be swept and reported, and partially suppresses error propagation.
- Defensible only as a **secondary experiment**, reported separately and clearly labelled.

### Recommendation

**(a) for the primary result.** It is the only option under which the headline comparison measures what the project claims to measure. (c) is a legitimate follow-up if time allows, provided it is never presented as the main result. (b) should be ruled out explicitly and the reasoning recorded, so it does not resurface later as an apparently reasonable idea.

**Downstream dependencies:** this decision determines [OQ-4](#oq-4--where-does-a-cold-start-seed-set-come-from) and the viability of the `confirmed_only` write policy ([03](./03-write-path.md#confirmed_only--store-only-externally-confirmed-verdicts)).

---

## OQ-3 — Where does `attack_category` come from?

**Status: open. Blocks the Phase 0 schema lock.**

[`CLAUDE.md`](../../CLAUDE.md) §66 lists "attack category" as stored metadata but never specifies its source. Three candidates, not equivalent:

| Source | Leakage | Notes |
|---|---|---|
| Detector's predicted class | None | Already captured as `detector_label`. Storing it again under another name adds nothing. |
| LLM's own categorization | None | A model output; can be wrong, which is acceptable and informative. |
| CICIDS2017 ground-truth label | **Yes** | The oracle leak from §87. Also usable as a `where` filter, which would be worse. |

### Recommendation

**The LLM's categorization**, as a distinct field from `detector_label`, drawn from a closed vocabulary so it is filterable and countable (`dos`, `ddos`, `port_scan`, `brute_force`, `web_attack`, `bot`, `infiltration`, `none`, `unknown`).

The divergence between `detector_label` and `attack_category` is itself worth reporting: where the LLM disagrees with the frozen detector, and whether memory makes it disagree more or less often, is a result in its own right.

**Needed from the team:** confirmation, plus the closed vocabulary. If ground truth is chosen, it must be argued against [OQ-2](#oq-2--does-ground-truth-feed-the-memory-store).

---

## OQ-4 — Where does a cold-start seed set come from?

**Status: open. Blocks Phase 3.** Depends on [OQ-2](#oq-2--does-ground-truth-feed-the-memory-store).

[`CLAUDE.md`](../../CLAUDE.md) §114 offers two paths: *"either warm-start with a seed set or report cold-start and steady-state separately."* The first needs a source for the seed cases, and every obvious source has a problem.

| Source | Problem |
|---|---|
| Ground-truth-labelled CICIDS2017 cases | The [OQ-2](#oq-2--does-ground-truth-feed-the-memory-store) leak, pre-loaded. Contaminates from alert #1. |
| A held-out slice replayed through Arm B first | Clean — the LLM triages it without labels — but it consumes data and must be excluded from scoring. Requires a documented split. |
| Hand-written synthetic cases | No leak, but they are the author's beliefs about what precedent should say, injected directly into the result. Hard to defend. |
| No seed set | Honest. Costs statistical power on shorter runs. |

### Recommendation

**No seed set for the primary result**, with cold-start and steady-state reported separately, split at the empirically observed hit-rate plateau ([R2](./06-risks-and-limitations.md#r2--cold-start)).

If a warm start is wanted as a secondary experiment, use **the held-out slice replayed through Arm B**: it is the only clean source, and it also demonstrates the more realistic deployment story — the system is run for a period to accumulate memory, then evaluated.

**Needed from the team:** a decision, and if warm-starting, the split definition and the seed slice's provenance recorded in this file.

---

## OQ-5 — What is the Phase 2 default write policy?

**Status: open. Blocks Phase 2.**

[`CLAUDE.md`](../../CLAUDE.md) §114 assigns the write-policy decision to Phase 3, but Phase 2 must implement the write path (§110–111) and therefore needs a working default before that sweep exists. The Phase 2 default is not a placeholder — it produces the first Arm B numbers, and those numbers tend to become the reference point.

### Recommendation

**`write_all`.** It is the honest baseline: it stores every triaged case including mistakes, which is what makes error propagation ([R1](./06-risks-and-limitations.md#r1--error-propagation)) observable rather than suppressed. Starting with a filtered policy would hide the effect [`CLAUDE.md`](../../CLAUDE.md) §133 requires be measured, and would require justifying the filter's parameters before there is any data to justify them with.

Phase 3 then sweeps `confidence_gated` against it, and the comparison is meaningful because the baseline is unfiltered.

**Needed from the team:** confirmation, and agreement that the Phase 2 numbers are labelled `write_all` in every report rather than quoted bare.

---

## OQ-6 — How many Arm B runs, and how are they aggregated?

**Status: open. Blocks Phase 4.** Not addressed in [`CLAUDE.md`](../../CLAUDE.md).

Arm B is stateful and, unless the LLM is at temperature 0, non-deterministic. One verdict differing early changes what gets written, which changes later retrievals, which changes later verdicts. **Small early differences compound** — this is a property Arm A does not have, since Arm A's alerts are independent.

Consequences:

- A single Arm B run is one sample from a distribution, not a measurement.
- Arm A and Arm B have different variance structures, so a single-run difference cannot be attributed to memory with any confidence.
- Even at temperature 0, LLM determinism is not guaranteed across API calls.

### Recommendation

**At least 3 Arm B runs and 3 Arm A runs**, differing only in LLM sampling seed with the alert sequence held fixed. Report mean and spread for every metric, not point estimates. If run-to-run spread in Arm B approaches the A-vs-B difference, **say so** — that is a real result about the stability of memory-augmented triage, and it is exactly the kind of finding a single-run study would miss.

**Needed from the team:** the run count, the LLM temperature, and whether the primary metric is reported as a mean difference with spread or as a paired per-alert comparison.

---

## OQ-7 — Does Arm B retrieve across runs?

**Status: open. Blocks Phase 2.** Not addressed in [`CLAUDE.md`](../../CLAUDE.md).

The project's stated goal is memory that persists "across shifts, analysts, and time" ([`CLAUDE.md`](../../CLAUDE.md) §23). Taken literally, memory should span runs. But a store that persists across runs makes run *n+1* incomparable to run *n* and breaks the identical-sequence guarantee ([R9](./06-risks-and-limitations.md#r9--memory-state-as-an-uncontrolled-variable)).

### The distinction to hold

- **Persistence as a product property** — memory survives process restart, is on disk, and is not lost when a session ends. This is Invariant #2 and is fully satisfied by a run-scoped store.
- **Persistence as an experimental condition** — memory carries across scored runs. This would destroy reproducibility.

They are different claims, and the project only needs the first. A run-scoped on-disk store demonstrates "knowledge persists beyond one analyst" perfectly well; the shift boundary is modelled *within* a run by the stream itself.

### Recommendation

**Run-scoped stores. No cross-run retrieval for scored runs.** Snapshots provide deliberate, declared carry-over when an experiment specifically calls for it ([05 §Operations](./05-configuration.md#operations)).

**Needed from the team:** confirmation, and agreement on how the persistence claim is worded in the writeup so it is not overstated.

---

## Recording decisions

When a question is resolved, edit its section here: change **Status: open** to **Status: decided YYYY-MM-DD**, state the choice, and give the reasoning — including what was rejected and why. Then update the affected doc and, where it changes an experimental condition, the run manifest schema.

Do not delete resolved questions. The rejected options and their reasoning are part of the methodology, and [`CLAUDE.md`](../../CLAUDE.md) §158 makes the documented limitations an academic deliverable in their own right.
