# 07 — Open Questions

> [`CLAUDE.md`](../../CLAUDE.md): *"Surface ambiguity; do not resolve it silently. Guessing on a settled-looking question is worse than pausing."* and *"Never invent dataset fields, metric definitions, or schema entries. If something is undefined, ask."*
>
> Each question below has a recommendation. **OQ-2 is decided** (2026-10-01); the rest are open. Every one changes what Phase 2 builds. Record the decision and its rationale in this file when made; a decision that lives only in a conversation is not a decision.

| ID | Question | Blocks | Recommendation | Status |
|---|---|---|---|---|
| [OQ-1](#oq-1--does-the-embedded-text-include-the-verdict) | Does the embedded text include the verdict? | Phase 0 schema lock | Alert-only (symmetric) | open |
| [OQ-2](#oq-2--does-ground-truth-feed-the-memory-store) | Does ground truth feed the memory store? | Phase 2 write path | No — oracle only | **decided 2026-10-01** |
| [OQ-3](#oq-3--where-does-attack_category-come-from) | Where does `attack_category` come from? | Phase 0 schema lock | LLM output | open |
| [OQ-4](#oq-4--where-does-a-cold-start-seed-set-come-from) | Where does a cold-start seed set come from? | Phase 3 | No seed; report phases separately | open |
| [OQ-5](#oq-5--what-is-the-phase-2-default-write-policy) | Phase 2 default write policy? | Phase 2 | `write_all` | open |
| [OQ-6](#oq-6--how-many-arm-b-runs-and-how-are-they-aggregated) | How many Arm B runs, aggregated how? | Phase 4 | ≥3 LLM seeds, report spread | open — paired test settled, see BL-017 |
| [OQ-7](#oq-7--does-memory-persist-across-runs) | Does memory persist across runs? | Phase 2 | No — run-scoped | open |
| [OQ-8](#oq-8--which-embedding-model-is-locked-for-phase-2) | Which embedding model is locked? | Phase 2 | MiniLM if measurement supports it | open — **measurement taken**, see below |
| [OQ-9](#oq-9--what-does-layer-2-emit) | What does Layer 2 emit? | Phase 0 schema lock | — team decision required | open — premise stale, see below |

---

## OQ-1 — Does the embedded text include the verdict?

**Status: open. Blocks the Phase 0 schema lock.**

### The inconsistency

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4 (Layer 3) contains two statements that cannot both be implemented:

> Write path: *"embed the case (alert features + context + verdict + rationale)"*
>
> Read path: *"embed the incoming alert with the same embedding model"*

An incoming alert has no verdict — it has not been triaged yet. So the write path would embed text containing verdict and rationale, and the read path would embed text without them. Same model, structurally different text. The "same embedding model" requirement is satisfied, but its *purpose* — comparable vectors — is not.

### Options

**(a) Alert-only text — symmetric.** The embedded document describes the alert. Verdict and rationale are metadata, retrieved with the case and injected into the prompt, but not part of what determines the match.

- Query and document are identically shaped. Similarity measures "does this alert look like that alert," which is the intended semantics.
- Verdict and rationale are still fully available to the LLM — they just do not steer retrieval.
- Cost: cases with identical flow characteristics but different verdicts are equally retrievable. Arguably correct — the LLM should see both and reason about the disagreement.

**(b) Full case text — asymmetric.** Embed alert + verdict + rationale on write; alert only on query.

- Matches the write-path bullet literally.
- Degrades similarity by an amount nobody has measured. Rationale text is natural language and will dominate a vector otherwise built from numeric strings, so retrieval drifts toward *rationale-similarity* rather than alert-similarity.
- Query vectors and document vectors occupy systematically different regions.

**(c) Full case text with a query-side placeholder.** Render the query with `VERDICT: pending / RATIONALE: unknown` to restore structural symmetry.

- Preserves the write-path bullet's intent while keeping the shapes aligned.
- The placeholder tokens are themselves a systematic difference, and the rationale-dominance problem in (b) remains.

### Recommendation

**(a).** It gives the retrieval semantics the system actually wants, keeps the paths genuinely symmetric, and loses nothing — verdict and rationale reach the LLM via metadata regardless. [02 — Case schema](./02-case-schema.md) is written against (a) and would need revision for (b) or (c).

**Needed from the team:** a decision, recorded here. If (b) or (c), also decide whether the rationale is truncated before embedding, since a 500-character rationale alone would consume most of the token budget ([R5](./06-risks-and-limitations.md#r5--silent-truncation-at-the-token-limit)).

---

## OQ-2 — Does ground truth feed the memory store?

**Status: decided 2026-10-01.** See [Decision](#decision--2026-10-01) at the end of this section. [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §5 asked for this decision and instructed that it not be silently made; [`CLAUDE.md`](../../CLAUDE.md) went further: *"The ground-truth handling question in `PROJECT_BRIEF.md` §5 is open. Do not implement either interpretation without confirmation."* The options and their reasoning are kept below because the rejected ones are part of the methodology.

### The tension

§5 establishes the working assumption: ground-truth labels are the **evaluation oracle only** — the detector produces alerts, the LLM produces verdicts, ground truth scores those verdicts afterwards.

§5 then names the hazard: if ground-truth labels *also* feed the memory store as confirmed verdicts, memory becomes an oracle rather than a realistic analyst record, and results inflate.

### Options

**(a) Oracle only — no ground truth in memory.** Memory stores what the LLM concluded, right or wrong.

- Realistic: it models a SOC where analysts record their own judgments, including mistakes.
- Preserves the validity of the comparison — Arm B's advantage comes from memory, not from labels.
- **Makes error propagation ([R1](./06-risks-and-limitations.md#r1--error-propagation)) possible, which is required** — [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §8 mandates testing it, and it cannot occur if stored verdicts are always correct.

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

### Decision — 2026-10-01

**Chosen: (a) for the primary result, with a declared oracle-confirmed condition alongside it as an upper bound.**

Memory stores the LLM's own verdicts, right or wrong. That is the condition every headline number is reported under. A second condition, identical in every other respect, stores oracle-confirmed verdicts instead; it is reported separately and is never the headline.

The two are one toggle on the memory module, not two codepaths — [`CLAUDE.md`](../../CLAUDE.md) § *Experimental Integrity* applies unchanged.

**Why both rather than (a) alone.** The gap between the two conditions *is* the cost of self-written feedback, measured rather than argued. [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §8 requires error propagation to be tested rather than mentioned, and (a) on its own shows only that propagation happened — it gives no ceiling to compare against, so it cannot separate a weak retriever from well-retrieved but wrong precedent.

**Why not (b).** Ruled out explicitly, as the recommendation above asked. Storing the true label makes retrieval a label lookup, hands the LLM the answer, and makes error propagation untestable by construction. It is recorded here as rejected so it does not resurface later as an apparently reasonable idea.

**Relation to (c).** This is close to the hybrid, but structured as a two-level factor rather than a review-rate sweep. There is no new `review_rate` parameter to justify: the conditions are "none confirmed" and "all confirmed", which bracket every intermediate rate without needing one chosen.

**Prompted by** the 2026-09-30 mentor review (`docs/research-paper/Review - MemSOC -30092026.docx` §C), which raised the same hazard independently — *"with 70% of attacks misclassified, memory would preserve and amplify those errors"* — and proposed the two-condition comparison as its RQ3. Sandbox measurement supports the concern: the nearest retrieved neighbour already carries the detector's own wrong attack family 70.8% of the time, before any LLM error has been stored (BL-014).

**Still open, and not settled by this decision:** [OQ-4](#oq-4--where-does-a-cold-start-seed-set-come-from). The primary condition writes no ground truth, so a ground-truth seed set remains the leak it always was; but the oracle-confirmed condition does not by itself justify a warm start either. Decide OQ-4 on its own terms.

**Implementation** is tracked as BL-015. BL-001 is closed by this decision.


---

## OQ-3 — Where does `attack_category` come from?

**Status: open. Blocks the Phase 0 schema lock.**

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4 (Layer 3) lists "attack category" as stored metadata but never specifies its source. Three candidates, not equivalent:

| Source | Leakage | Notes |
|---|---|---|
| Detector's predicted class | None | Already captured as `detector_label`. Storing it again under another name adds nothing. |
| LLM's own categorization | None | A model output; can be wrong, which is acceptable and informative. |
| Dataset ground-truth label | **Yes** | The oracle leak from §5. Also usable as a `where` filter, which would be worse. |

### Recommendation

**The LLM's categorization**, as a distinct field from `detector_label`.

The divergence between the two is itself worth reporting: where the LLM disagrees with the frozen detector, and whether memory makes it disagree more or less often, is a result in its own right.

**Also needed: the vocabulary itself.** For `attack_category` to be filterable and countable it must be a closed set. That set should follow the label taxonomy fixed by Phase 0 preprocessing — it is **not** something to invent in this doc ([`CLAUDE.md`](../../CLAUDE.md): never invent dataset fields or schema entries). It therefore depends on [OQ-9](#oq-9--what-does-layer-2-emit).

**Needed from the team:** confirmation of the source, plus the closed vocabulary once the label taxonomy is settled. If ground truth is chosen, it must be argued against [OQ-2](#oq-2--does-ground-truth-feed-the-memory-store).

---

## OQ-4 — Where does a cold-start seed set come from?

**Status: open. Blocks Phase 3.** Depends on [OQ-2](#oq-2--does-ground-truth-feed-the-memory-store).

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 Phase 3 offers two paths: *"either warm-start with a seed set or report cold-start and steady-state separately."* The first needs a source for the seed cases, and every obvious source has a problem.

| Source | Problem |
|---|---|
| Ground-truth-labelled cases | The [OQ-2](#oq-2--does-ground-truth-feed-the-memory-store) leak, pre-loaded. Contaminates from alert #1. |
| A held-out slice replayed through Arm B first | Clean — the LLM triages it without labels — but it consumes data and must be excluded from scoring. Requires a documented split. |
| Hand-written synthetic cases | No leak, but they are the author's beliefs about what precedent should say, injected directly into the result. Hard to defend. |
| No seed set | Honest. Costs statistical power on shorter runs. |

### Recommendation

**No seed set for the primary result**, with cold-start and steady-state reported separately, split at the empirically observed hit-rate plateau ([R2](./06-risks-and-limitations.md#r2--cold-start)).

If a warm start is wanted as a secondary experiment, use **the held-out slice replayed through Arm B**: it is the only clean source, and it also demonstrates the more realistic deployment story — the system is run for a period to accumulate memory, then evaluated. Note that constructing such a split touches the alert stream, which is a protected component; it needs explicit approval, not a quiet re-partition.

**Needed from the team:** a decision, and if warm-starting, the split definition and the seed slice's provenance recorded in this file.

---

## OQ-5 — What is the Phase 2 default write policy?

**Status: open. Blocks Phase 2.**

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 assigns the write-policy decision to Phase 3, but Phase 2 must implement the write path and therefore needs a working default before that sweep exists. The Phase 2 default is not a placeholder — it produces the first Arm B numbers, and those numbers tend to become the reference point.

### Recommendation

**`write_all`.** It is the honest baseline: it stores every triaged case including mistakes, which is what makes error propagation ([R1](./06-risks-and-limitations.md#r1--error-propagation)) observable rather than suppressed. Starting with a filtered policy would hide the effect [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §8 requires be measured, and would require justifying the filter's parameters before there is any data to justify them with.

Phase 3 then sweeps `confidence_gated` against it, and the comparison is meaningful because the baseline is unfiltered.

**Needed from the team:** confirmation, and agreement that the Phase 2 numbers are labelled `write_all` in every report rather than quoted bare.

---

## OQ-6 — How many Arm B runs, and how are they aggregated?

**Status: open. Blocks Phase 4.** Not addressed in [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md).

Arm B is stateful and, unless the LLM is at temperature 0, non-deterministic. One verdict differing early changes what gets written, which changes later retrievals, which changes later verdicts. **Small early differences compound** — a property Arm A does not have, since Arm A's alerts are independent.

Consequences:

- A single Arm B run is one sample from a distribution, not a measurement.
- Arm A and Arm B have different variance structures, so a single-run difference cannot be attributed to memory with any confidence.
- Even at temperature 0, LLM determinism is not guaranteed across API calls.

### The constraint this must respect

The **alert stream order and seeds are a protected component** — [`CLAUDE.md`](../../CLAUDE.md): *deterministic and reproducible; never reshuffle, resample, or reseed.* Multiple runs must therefore vary **only the LLM sampling seed**, with the alert sequence byte-identical across every run in both arms. Varying the stream seed to get "more samples" would break the identical-sequence guarantee in [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §3 and is not an available option.

### Recommendation

**At least 3 Arm B runs and 3 Arm A runs**, differing only in LLM sampling seed, alert sequence held fixed. Report mean and spread for every metric, not point estimates. If run-to-run spread in Arm B approaches the A-vs-B difference, **say so** — that is a real result about the stability of memory-augmented triage, and exactly the kind of finding a single-run study would miss.

**Needed from the team:** the run count, the LLM temperature, and whether the primary metric is reported as a mean difference with spread or as a paired per-alert comparison. Note that the metric definition is a protected component, so this must be settled before results exist, not after.

---

## OQ-7 — Does memory persist across runs?

**Status: open. Blocks Phase 2.** Not addressed in [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md).

The project's stated goal is memory that persists "across shifts, analysts, and time" ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §2). Taken literally, memory should span runs. But a store that persists across runs makes run *n+1* incomparable to run *n* and breaks the identical-sequence guarantee ([R9](./06-risks-and-limitations.md#r9--memory-state-as-an-uncontrolled-variable)).

### The distinction to hold

- **Persistence as a product property** — memory survives process restart, is on disk, and is not lost when a session ends. This is Invariant #2 and is fully satisfied by a run-scoped store.
- **Persistence as an experimental condition** — memory carries across scored runs. This would destroy reproducibility.

They are different claims, and the project only needs the first. A run-scoped on-disk store demonstrates "knowledge persists beyond one analyst" perfectly well; the shift boundary is modelled *within* a run by the stream itself.

### Recommendation

**Run-scoped stores. No cross-run retrieval for scored runs.** Snapshots provide deliberate, declared carry-over when an experiment specifically calls for it ([05 §Operations](./05-configuration.md#operations)).

This also resolves cleanly against the protected-component rule on the case store: because each run creates its own directory, no run ever needs to clear another's ([01 §Store lifecycle](./01-architecture.md#store-lifecycle-and-reproducibility)).

**Needed from the team:** confirmation, and agreement on how the persistence claim is worded in the writeup so it is not overstated.

---

## OQ-8 — Which embedding model is locked for Phase 2?

**Status: open. Blocks Phase 2.**

[`CLAUDE.md`](../../CLAUDE.md) makes the embedding model a protected component: *never swap or change versions.* [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 Phase 2 says to lock the embedding function at the start of that phase. Together, these mean the choice is effectively **irreversible from Phase 2 onward** — a later swap requires explicit approval and re-rendering every stored case into a new store.

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §6 names `all-MiniLM-L6-v2` as an example ("e.g."), not a commitment. The decision therefore still has to be made deliberately, and the one measurement that could invalidate it has not been taken.

### What has to be measured first

Under the **final** case template ([02](./02-case-schema.md#template--draft-pending-oq-9)), which itself depends on [OQ-9](#oq-9--what-does-layer-2-emit):

- p50 and p99 rendered token length.
- Headroom against the model's max sequence length (256 for MiniLM).

If p99 approaches the limit, cases are silently truncated and similarity degrades unpredictably ([R5](./06-risks-and-limitations.md#r5--silent-truncation-at-the-token-limit)). The two ways out — trim the template, or choose a model with a longer sequence limit — are both cheap *before* the lock and expensive after.

### Measurement taken — 2026-09-28

Measured with MiniLM's own tokenizer over 211 rendered alerts, counting `[CLS]` and `[SEP]`. Full detail in `../../../memsoc-sandbox/FINDINGS.md`; tracked as BL-013.

| Template | p50 | p95 | p99 | max | Truncated |
|---|---|---|---|---|---|
| Draft ([02](./02-case-schema.md#template--draft-pending-oq-9), 11 lines, full labels) | 260 | 268 | 273 | 278 | **179 / 211** |
| Compact (same fields, terse labels) | 144 | — | 157 | 162 | 0 / 211 |

**The draft template does not fit.** The earlier heuristic p99 of ~184 was 89 tokens low, because numbers split into several word-pieces (`16383` becomes `163` + `##83`). So the condition this question set — *lock MiniLM if and only if the measurement shows comfortable headroom* — fails for the draft template and passes comfortably for a compact rendering of the same fields.

**Truncation is silent, as [R5](./06-risks-and-limitations.md#r5--silent-truncation-at-the-token-limit) warned.** A 313-token case embedded with no error or warning, and its vector was bit-identical to the vector of its first 256 tokens; rewriting every digit past the cut changed nothing. Whatever template is locked, the renderer needs a hard assertion on token count rather than trust.

**What this does not settle.** Choosing between the two templates on retrieval quality would be tuning on the test set — they scored identically (P@1 0.640 both). The defensible basis for preferring the compact one is that it fits the limit. The lock itself, and its version pin, still need approval.


### Recommendation

**Lock `all-MiniLM-L6-v2` if and only if the token measurement shows comfortable headroom.** It is the model already named in the brief, it runs locally with no API dependency, and staying with it avoids relitigating a settled-looking choice.

If the measurement shows the template does not fit, that is a decision for the team, taken in Phase 0 — not a mid-Phase-2 substitution.

**Needed from the team:** approval of the locked model and its version pin, on the basis of the token-length measurement, before Phase 2 begins.

---

## OQ-9 — What does Layer 2 emit?

**Status: open. Blocks the Phase 0 schema lock.**

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 Phase 0 adds: *"Find the right OS ML model and define the output format. Complete data consistency should be maintained between layers."* The detector has not been chosen, so the memory layer's input contract does not exist yet — and several schema fields are inherited directly from it ([02 §The Layer 2 input contract](./02-case-schema.md#the-layer-2-input-contract)).

[`CLAUDE.md`](../../CLAUDE.md) forbids inventing dataset fields or schema entries, so these stay marked **pending** rather than being guessed.

### What this layer needs settled

| Question | Why it blocks the schema |
|---|---|
| Does the detector expose a **confidence/score** per alert, or only a predicted class? | `detector_score` is rendered into the embedding text and gates the `confidence_gated` write policy. If no score exists, both uses must be removed — a design change, not a detail. |
| What is the **label vocabulary**, and is it closed and stable? | Becomes `detector_label`, and constrains the `attack_category` vocabulary in [OQ-3](#oq-3--where-does-attack_category-come-from). |
| Which **columns survive preprocessing**? | The embedding template can only render fields that exist. If identity columns (addresses, ports, protocol, timestamps) are dropped, the template loses its two most semantically meaningful lines and similarity becomes almost purely numeric — the worst case for [R7](./06-risks-and-limitations.md#r7--numeric-features-in-a-text-embedding-space). |
| Is there a **stable alert identifier** carried through the stream? | Required to join a stored case back to its alert, its ground-truth label, and its scoring record — the "complete data consistency between layers" requirement. |
| Is a **detector version identifier** recorded? | Becomes `detector_version`; makes an accidental detector change detectable after the fact. |

### Recommendation

No recommendation — this is a Layer 2 decision and out of scope for these docs. The memory layer's ask is only that the contract be **written down and stable** before the case schema is locked, and that it include a per-alert score and a stable alert identifier.

**Needed from the team:** the settled output format, recorded wherever Layer 2 is documented. Once it exists, the pending fields in [02](./02-case-schema.md) can be filled in and the schema locked.

### The premise is stale — verified 2026-10-01

"The detector has not been chosen" is no longer true. It is the frozen LightGBM multiclass model in `models/multiclass_lightgbm.pkl`. Four of the five questions above are answered by what it already emits, read directly from `artifacts/model_outputs/live_results.jsonl`:

| Question | Answer |
|---|---|
| Per-alert confidence, or class only? | Both. `multiclass.confidence` per alert, plus `binary_confidence`, plus a per-alert `alert.shap_explanation`. |
| Label vocabulary — closed and stable? | Closed, eight attack families, all observed in output: `Exploits`, `Fuzzers`, `Reconnaissance`, `DoS`, `Generic`, `Backdoor`, `Analysis`, `Shellcode`. No `Benign`, no `Worms`. |
| Which columns survive preprocessing? | 48 of 55. Dropped: the two targets plus `IPV4_SRC_ADDR`, `IPV4_DST_ADDR`, `FLOW_START_MILLISECONDS`, `FLOW_END_MILLISECONDS`, `DNS_QUERY_ID`. Addresses are therefore absent by construction, which is what the template needs. |
| Stable alert identifier? | Yes, `uid`, carried from generation through capture to `ground_truth.csv`. |
| Detector version identifier? | **No — this is the remaining gap.** Nothing in `src/memsoc/detection/` or in the emitted records states which model produced an alert, so `detector_version` cannot be populated. Tracked as BL-075. |

Two cautions for anyone rendering a case from these records. The record carries `src_ip` and `dst_ip` at **top level** even though the nested `alert` sub-record does not, so a renderer must select fields by explicit whitelist (BL-026). And four of the 48 features are unusable as text: `SRC_TO_DST_SECOND_BYTES` and `DST_TO_SRC_SECOND_BYTES` hold `inf` for zero-duration flows, `SRC_TO_DST_IAT_MIN` is zero in 99.9% of rows and `DST_TO_SRC_IAT_MIN` in 100%.

This question stays **open** only for the one missing field and for the contract being written down where Layer 2 is documented, rather than inferred from sample output as it is here.


---

## Recording decisions

When a question is resolved, edit its section here: change **Status: open** to **Status: decided YYYY-MM-DD**, state the choice, and give the reasoning — including what was rejected and why. Then update the affected doc and, where it changes an experimental condition, the run manifest schema.

Do not delete resolved questions. The rejected options and their reasoning are part of the methodology, and [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §10 makes the documented limitations an academic deliverable in their own right.
