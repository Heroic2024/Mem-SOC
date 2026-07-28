# Memory Layer — Documentation

> Layer 3 of the four-layer Agentic SOC system. See [`CLAUDE.md`](../../CLAUDE.md) §4 and §6 for the authoritative project brief.

This directory documents **the memory layer only**. It is the research variable — the single component that differs between Arm A and Arm B. Everything documented here exists to make that variable precise, reproducible, and honestly measurable.

---

## What the memory layer is

A persistent, on-disk vector store of past triaged cases, plus the read and write logic that surrounds it.

- **Write path** — after a case is triaged, render it to text, embed it, and store the vector alongside filterable metadata.
- **Read path** — when a new alert arrives, embed it with the *same* model, run top-k similarity search, filter, threshold, and inject surviving cases into the LLM prompt as precedent.

That is the whole layer. It does not classify, it does not decide, and it does not score. It supplies precedent and it remembers outcomes.

## Why it is the crux

The research contribution is not a better detector and not a novel retrieval algorithm ([`CLAUDE.md`](../../CLAUDE.md) §1). It is the isolation and measurement of what memory contributes to LLM alert triage. The detector, the LLM, the prompt template, and the alert sequence are all frozen. If a measured difference between arms can be attributed to anything other than this layer, the experiment is invalid.

Every design choice documented here is therefore held to a stricter standard than normal engineering: it must be *identical across arms except where the memory layer is the thing being toggled*.

---

## Document index

| Doc | Covers |
|---|---|
| [01 — Architecture](./01-architecture.md) | Components, read/write path sequences, module boundaries, arm-toggling, state lifecycle |
| [02 — Case schema](./02-case-schema.md) | What gets embedded vs. what becomes metadata, field-by-field, ID scheme, worked example |
| [03 — Write path](./03-write-path.md) | When and what to write, write policies, error propagation and its test, ground-truth boundary |
| [04 — Read path](./04-read-path.md) | Query embedding, top-k, metadata filters, similarity threshold, prompt injection format, tuning |
| [05 — Configuration](./05-configuration.md) | ChromaDB setup, embedding model pinning, persistence, config surface, operational commands |
| [06 — Risks & limitations](./06-risks-and-limitations.md) | Failure modes specific to this layer, how each is detected, mitigated, and reported |
| [07 — Open questions](./07-open-questions.md) | Decisions the team must make before Phase 2 locks. **Read this before implementing.** |

---

## Invariants

These are non-negotiable. Violating any one of them invalidates the comparison.

1. **One embedding model, both paths.** The model that embeds a case on write is byte-identical to the model that embeds a query on read — same checkpoint, same version, same normalization, same pooling. Mismatched models make cosine similarity meaningless. ([`CLAUDE.md`](../../CLAUDE.md) §68)
2. **Persistent mode from day one.** On-disk from the first commit. In-memory mode would make the "memory persists across shifts" claim literally false. ([`CLAUDE.md`](../../CLAUDE.md) §69)
3. **Arm A touches nothing.** No reads, no writes, no embedding calls, no latency contribution. Arm A is Arm B with the memory module disabled, not a separate codepath. ([`CLAUDE.md`](../../CLAUDE.md) §9)
4. **Query and document text are symmetric.** Whatever fields the read path embeds, the write path embeds the same fields in the same template. See [02 — Case schema](./02-case-schema.md) and [OQ-1](./07-open-questions.md#oq-1--does-the-embedded-text-include-the-verdict).
5. **Ground truth never enters the vector store as a retrievable field** unless the team explicitly decides otherwise and documents that decision. See [OQ-2](./07-open-questions.md#oq-2--does-ground-truth-feed-the-memory-store).
6. **Store state is reset to a known point before every scored run.** Otherwise the "identical alert sequence" guarantee is broken by leftover state. See [01 — Architecture](./01-architecture.md#state-lifecycle-and-reproducibility).
7. **Every retrieval is logged.** Case IDs, distances, filters applied, and what survived the threshold — for every alert, in both arms (Arm A logs an empty retrieval). Without this, the qualitative rationale-quality metric in Phase 4 cannot be computed.

---

## Out of scope for these docs

Deliberately excluded, per the instruction to focus only on this layer:

- The CICIDS2017 replay harness and its determinism guarantees (Layer 1)
- Training, freezing, and evaluating the ML detector (Layer 2)
- LLM prompt engineering, verdict parsing, and report generation (Layer 4)
- The experiment protocol, scoring harness, and metric definitions (Phase 4)
- Repo structure and build tooling

Where those touch the memory layer, this documentation defines only the **interface** — what the memory layer consumes and what it emits.
