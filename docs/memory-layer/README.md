# Memory Layer — Documentation

> Layer 3 of the four-layer Agentic SOC system. Design context: [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4 and §6. Agent operating rules: [`CLAUDE.md`](../../CLAUDE.md).

This directory documents **the memory layer only**. It is the research variable — the single component that differs between Arm A and Arm B. Everything documented here exists to make that variable precise, reproducible, and honestly measurable.

---

## What the memory layer is

A persistent, on-disk vector store of past triaged cases, plus the read and write logic that surrounds it.

- **Write path** — after a case is triaged, render it to text, embed it, and store the vector alongside filterable metadata.
- **Read path** — when a new alert arrives, embed it with the *same* model, run top-k similarity search, filter, threshold, and inject surviving cases into the LLM prompt as precedent.

That is the whole layer. It does not classify, it does not decide, and it does not score. It supplies precedent and it remembers outcomes.

## Why it is the crux

The research contribution is not a better detector and not a novel retrieval algorithm ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §1). It is the isolation and measurement of what memory contributes to LLM alert triage. The detector, the LLM, the prompt template, and the alert sequence are all frozen. If a measured difference between arms can be attributed to anything other than this layer, the experiment is invalid.

Every design choice documented here is therefore held to a stricter standard than normal engineering: it must be *identical across arms except where the memory layer is the thing being toggled*.

---

## Document index

| Doc | Covers |
|---|---|
| [01 — Architecture](./01-architecture.md) | Components, read/write path sequences, module boundaries, arm-toggling, store lifecycle |
| [02 — Case schema](./02-case-schema.md) | What gets embedded vs. what becomes metadata, field-by-field, ID scheme, worked example |
| [03 — Write path](./03-write-path.md) | When and what to write, write policies, error propagation and its test, ground-truth boundary |
| [04 — Read path](./04-read-path.md) | Query embedding, top-k, metadata filters, similarity threshold, prompt injection format, tuning |
| [05 — Configuration](./05-configuration.md) | ChromaDB setup, embedding model pinning, persistence, config surface, operational commands |
| [06 — Risks & limitations](./06-risks-and-limitations.md) | Failure modes specific to this layer, how each is detected, mitigated, and reported |
| [07 — Open questions](./07-open-questions.md) | Decisions the team must make before Phase 2 locks. **Read this before implementing.** |

---

## Status

These documents are **Phase 0 design proposals**, not a record of built software. Nothing described here is implemented.

Two things block the case schema from being locked:

- The nine [open questions](./07-open-questions.md). [OQ-2](./07-open-questions.md#oq-2--does-ground-truth-feed-the-memory-store) is explicitly reserved for the team — [`CLAUDE.md`](../../CLAUDE.md) states the [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §5 question is open and that neither interpretation may be implemented without confirmation.
- The **Layer 2 output contract.** [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 Phase 0 now requires finding the detection model and defining its output format, with "complete data consistency maintained between layers." The detector has not been chosen, so the fields this layer inherits from it are placeholders. See [02 §The Layer 2 input contract](./02-case-schema.md#the-layer-2-input-contract) and [OQ-9](./07-open-questions.md#oq-9--what-does-layer-2-emit).

[`CLAUDE.md`](../../CLAUDE.md) forbids inventing dataset fields or schema entries. Where a field here is not yet derivable from a settled upstream decision, it is marked **pending** rather than asserted.

---

## Invariants

These are non-negotiable. Violating any one of them invalidates the comparison.

1. **One embedding model, both paths.** The model that embeds a case on write is byte-identical to the model that embeds a query on read — same checkpoint, same version, same normalization, same pooling. Mismatched models make cosine similarity meaningless. ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4, Layer 3)
2. **Persistent mode from day one.** On-disk from the first commit. In-memory mode would make the "memory persists across shifts" claim literally false. ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4, Layer 3; [`CLAUDE.md`](../../CLAUDE.md), Code & Repo Rules)
3. **Arm A touches nothing.** No reads, no writes, no embedding calls, no latency contribution. Arm A is Arm B with the memory module disabled, not a separate codepath. [`CLAUDE.md`](../../CLAUDE.md) requires this be *verified before any baseline run*, not assumed.
4. **Query and document text are symmetric.** Whatever fields the read path embeds, the write path embeds the same fields in the same template. See [02](./02-case-schema.md) and [OQ-1](./07-open-questions.md#oq-1--does-the-embedded-text-include-the-verdict).
5. **Ground truth never enters the vector store as a retrievable field** unless the team explicitly decides otherwise and documents that decision. See [OQ-2](./07-open-questions.md#oq-2--does-ground-truth-feed-the-memory-store).
6. **The store is never deleted, wiped, or regenerated.** A fresh run gets a *new* directory; it does not clear an old one. See [01 §Store lifecycle](./01-architecture.md#store-lifecycle-and-reproducibility).
7. **Every decision is logged well enough to reconstruct** — alert ID, retrieved case IDs, similarity scores, verdict, rationale — in both arms, with Arm A logging an empty retrieval. Required by [`CLAUDE.md`](../../CLAUDE.md) and by the Phase 4 rationale-quality metric.

## Protected components touching this layer

[`CLAUDE.md`](../../CLAUDE.md) freezes the following by experimental design. Any task that appears to require changing one is a signal to **ask, not proceed**:

| Component | How it constrains this layer |
|---|---|
| Embedding model | Never swap or change versions. The choice must therefore be made *and justified* in Phase 0, before lock — see [05](./05-configuration.md#embedding-model) and [OQ-8](./07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2). |
| Base prompt template | One object, identical across arms, no per-arm wording. The precedent block is a *conditional section* of that object, not a variant of it. See [04](./04-read-path.md#prompt-injection-format). |
| Stored vector DB / case store | Never delete, wipe, or regenerate without explicit instruction. Shapes the entire store lifecycle design — see [01](./01-architecture.md#store-lifecycle-and-reproducibility). |
| Detection model weights & thresholds | Frozen. This layer *consumes* detector output and must never feed back into it. |
| Alert stream order & seeds | Never reshuffle, resample, or reseed. Constrains [OQ-6](./07-open-questions.md#oq-6--how-many-arm-b-runs-and-how-are-they-aggregated). |
| Evaluation harness & metric definitions | Not edited while implementing this layer; not adjusted after seeing results. |

---

## Out of scope for these docs

Deliberately excluded, per the instruction to focus only on this layer:

- The CICIDS2017 replay harness and its determinism guarantees (Layer 1)
- Selecting, training, freezing, and evaluating the ML detector (Layer 2)
- LLM prompt engineering, verdict parsing, and report generation (Layer 4)
- The experiment protocol, scoring harness, and metric definitions (Phase 4)
- Repo structure and build tooling

Where those touch the memory layer, this documentation defines only the **interface** — what the memory layer consumes and what it emits.
