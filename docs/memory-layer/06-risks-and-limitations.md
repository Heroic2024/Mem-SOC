# 06 — Risks & Limitations of the Memory Layer

> Scoped to failure modes originating in Layer 3. Project-wide risks (dataset age, frozen detector, ground-truth oversimplification) are in [`CLAUDE.md`](../../CLAUDE.md) §8 and are not restated here except where the memory layer changes their character.
>
> [`CLAUDE.md`](../../CLAUDE.md) §131: *"These must be documented, not buried. They are part of the honest contribution."*

---

## R1 — Error propagation

**Severity: critical.** [`CLAUDE.md`](../../CLAUDE.md) §133 — "the single most important failure mode."

A mis-triaged case, once stored, becomes retrievable precedent. Similar alerts retrieve it, the LLM anchors on it, and the error repeats — with each repetition writing another confirming instance, so later alerts see *multiple consistent* precedents for a wrong verdict. The failure compounds rather than merely persisting.

- **Detection:** the propagation graph built from `precedent_used` ([02](./02-case-schema.md#triage-output-layer-4)). Contamination is reachability from a wrong verdict.
- **Mitigation:** write policy ([03](./03-write-path.md#write-policies)) reduces exposure but cannot eliminate it — a confidently wrong verdict passes a confidence gate.
- **Test:** the injection experiment ([03 §The test](./03-write-path.md#the-test)). Required, not optional.
- **Report:** contamination rate, flip rate, amplification, and decay, across several injection points.

**This is not only a risk to be mitigated — it is a finding to be measured.** Suppressing it with an aggressive write policy would remove the phenomenon the project set out to study.

---

## R2 — Cold start

**Severity: high — affects every headline number.** [`CLAUDE.md`](../../CLAUDE.md) §134.

Memory begins empty. The first *n* alerts get no precedent and are, by construction, Arm A. Aggregate metrics therefore blend a memoryless phase with a memory-augmented one and understate steady-state performance by an amount that depends entirely on run length.

- **Detection:** `collection_count` logged at every retrieval ([04](./04-read-path.md#latency-and-token-accounting)); plot retrieval hit rate against it.
- **Mitigation:** report cold-start and steady-state separately, splitting at the empirical hit-rate plateau. Warm-starting is the alternative, but a seed set is a contamination hazard — [OQ-4](./07-open-questions.md#oq-4--where-does-a-cold-start-seed-set-come-from).
- **Report:** the split point, its justification, and metrics for both phases. A single blended number is not a defensible headline.

> **The comparison is longer-run-favourable.** Arm B's advantage grows with stream length, so run length is itself a parameter that shapes the result. State it explicitly rather than letting a chosen stream length quietly set the outcome.

---

## R3 — Retrieval noise

**Severity: high.** [`CLAUDE.md`](../../CLAUDE.md) §135.

Poorly chosen `k` or an absent threshold injects irrelevant "precedent," which can make Arm B **worse** than Arm A. Cosine similarity between rendered flow descriptions measures textual resemblance, not security relevance — two flows can render similarly and mean entirely different things.

- **Detection:** the manual relevance audit ([04 §Retrieval quality audit](./04-read-path.md#retrieval-quality-audit)), which yields a relevance-versus-similarity curve.
- **Mitigation:** set `τ_read` **from that curve**, not from intuition. Include `τ_read = 0.0` in the sweep as the explicit no-threshold control.
- **Report:** the curve, the chosen threshold, and its justification.

---

## R4 — Embedding-model mismatch

**Severity: critical, silent.** [`CLAUDE.md`](../../CLAUDE.md) §68 — "non-negotiable."

If write-path and read-path embeddings come from different models, versions, or normalization settings, similarity is meaningless. Nothing raises. Retrieval keeps returning results, they are simply wrong, and the run looks healthy.

- **Mitigation:** one model instance per process, shared by construction ([05 §Determinism](./05-configuration.md#determinism)); reference-corpus hash checked at startup; exact package pins.
- **Adjacent trap:** `schema_version`. Same model, different text template, same silent corruption. The store must refuse mixed versions ([02 §Schema versioning](./02-case-schema.md#schema-versioning)).

---

## R5 — Silent truncation at the token limit

**Severity: high, silent, and specific to this dataset.**

`all-MiniLM-L6-v2` truncates at 256 word-piece tokens. A rendered case that exceeds it produces a valid 384-dim vector computed from partial text — the tail features contribute nothing, and which features are lost varies with the width of the numeric values. Two otherwise-similar flows can lose different fields.

- **Detection:** token-length distribution measured in Phase 0; a hard assertion in `CaseRenderer`.
- **Mitigation:** template sized with headroom, or a 512-token model ([05 §If the template will not fit](./05-configuration.md#if-the-template-will-not-fit)).
- **Report:** the observed p50/p99 token length under the final template.

---

## R6 — Near-duplicate saturation

**Severity: medium-high. Expected, not hypothetical.**

CICIDS2017 attack bursts contain thousands of near-identical flows. Under `write_all`, memory fills with them, and top-*k* returns *k* copies of one case. Effective *k* collapses toward 1, prompt tokens are spent on redundancy, and — worse — a wrong verdict inside a burst is retrieved *k* times, amplifying R1.

- **Detection:** mean pairwise similarity within retrieved sets; distinct `flow_id` count per retrieval.
- **Mitigation:** diversity cap in the read path ([04 §Near-duplicate saturation](./04-read-path.md#near-duplicate-saturation)). Not on write — write-side dedup would erase the volume information that makes a flood identifiable as a flood.
- **Report:** saturation statistics with and without the diversity constraint.

---

## R7 — Numeric features in a text embedding space

**Severity: medium. Structural to the approach.**

Sentence transformers are trained on natural language. Rendering flow statistics as text and embedding them is a pragmatic choice, not a principled one: the model has no notion that `412 pkt/s` and `408 pkt/s` are near-identical while `412` and `4120` are an order of magnitude apart. Digit-level tokenization gives only a loose approximation of numeric proximity.

- **Consequence:** similarity is driven substantially by categorical and lexical fields (protocol name, port name, detector label) and by *formatting* of the numbers, more than by their magnitudes.
- **Mitigation:** deliberate rendering rules — resolved protocol/port names, fixed precision, human-readable magnitudes ([02 §Rendering rules](./02-case-schema.md#rendering-rules)).
- **Honest framing for the writeup:** this evaluates *a* reasonable memory-layer implementation, not the best achievable one. A hybrid retriever over scaled numeric features would likely retrieve better — and would also be a second variable, which is why it is out of scope here.
- **Report:** state this as a limitation on the generality of the result.

---

## R8 — ChromaDB scaling characteristics

**Severity: low for this project. Documented because [`CLAUDE.md`](../../CLAUDE.md) §98 requires it.**

Documented limitations: high memory usage at scale, due to reliance on in-memory operations; limited scalability for workloads in the millions of vectors, where Pinecone, Weaviate, or Milvus perform better.

- **Impact here: none.** A controlled comparison over a fixed dataset produces thousands to low tens of thousands of vectors, far inside Chroma's comfortable range, and its Apache-2.0 licence, disk persistence, metadata filtering, and fast setup are the right trade for a research prototype ([`CLAUDE.md`](../../CLAUDE.md) §93).
- **Where it would matter:** production SOC volumes. Real deployments generate millions of alerts per year, and at that scale both limitations become live and the choice warrants re-evaluation.
- **Design consequence already taken:** rationales and full feature vectors live in the sidecar, not in Chroma metadata, keeping the resident footprint proportional to what is actually filtered on ([02 §Part 3](./02-case-schema.md#part-3--sidecar-record)).

---

## R9 — Memory state as an uncontrolled variable

**Severity: high. Unique to Arm B — there is no analogue in Arm A.**

The store is stateful, so Arm B's output depends on its starting state as much as on the alert sequence. Re-running against a populated store makes alert #1 retrieve precedent it could not have had, and the run is silently non-comparable.

- **Mitigation:** run-scoped store paths; declared `initial_state`; automated `reset()`; hard failure when a scored run starts against an undeclared non-empty store ([01 §State lifecycle](./01-architecture.md#state-lifecycle-and-reproducibility)).
- **Report:** `initial_state`, start count, end count, and case-ID hash in every manifest.

---

## R10 — Memory as a confound in the latency metric

**Severity: low, but it distorts a reported number.**

The token-and-latency overhead metric ([`CLAUDE.md`](../../CLAUDE.md) §121) attributes cost to the memory layer. If Arm A loads the embedding model, opens a store handle, or pays any part of the retrieval path, the measured overhead is understated and the comparison flatters Arm B.

- **Mitigation:** `NullMemoryLayer` loads nothing and opens nothing ([05 §Startup checklist](./05-configuration.md#startup-checklist)).
- **Also:** retrieval latency grows with `collection_count`, so a single average is misleading. Report latency as a function of store size.

---

## Standing constraint

[`CLAUDE.md`](../../CLAUDE.md) §140: **a negative or null result is a legitimate outcome.**

Every mitigation above is a defensible engineering choice *and* a degree of freedom that could be tuned until Arm B wins. The protections against that are procedural, not technical:

- `τ_read` is set from the measured relevance curve, before final scoring — not adjusted afterwards.
- The write policy is declared before the run, not selected after seeing results.
- Every swept configuration is reported, not only the best one.
- Cold-start and steady-state splits are defined by the hit-rate plateau, not chosen to favour an outcome.

If Arm B loses under an honestly configured memory layer, that is the finding — and R3, R6, and R7 above are the explanation for *why*, which is a more useful contribution than a tuned win.
