# 01 — Memory Layer Architecture

> Scope: Layer 3 only. Layers 1, 2, and 4 appear here solely as interface boundaries.
>
> Design context: [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4 and §9.

---

## Position in the system

```
[1] DATA STREAM  →  [2] DETECTION (ML)  →  [3] MEMORY (Vector DB)  →  [4] LLM TRIAGE + REPORTING
                                                    ↑______________________________|
                                                          (write-back loop)
```

The linear diagram in [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4 is a data-flow sketch, not an execution order. The memory layer is touched **twice per alert**, straddling Layer 4:

```
alert ──► [3] READ  ──► precedent ──► [4] LLM TRIAGE ──► verdict ──► [3] WRITE ──► store
```

Read happens *before* triage. Write happens *after*. Both are the same layer and share the same embedding function and the same store handle.

---

## Components

| Component | Responsibility | Notes |
|---|---|---|
| **`EmbeddingFunction`** | Text → vector | Single instance, loaded once, shared by read and write. Invariant #1. A **protected component** — never swapped after lock. |
| **`CaseRenderer`** | Alert/case record → embedding text + metadata dict | Deterministic and pure. The only place the text template lives. See [02](./02-case-schema.md). |
| **`MemoryStore`** | ChromaDB persistent collection wrapper | Owns the client, collection, distance space, and persistence path. |
| **`Retriever`** | Query → ranked, filtered, thresholded precedent list | Owns top-k, `where` filters, threshold cutoff, and distance→similarity conversion. See [04](./04-read-path.md). |
| **`Writer`** | Triaged case → store commit | Owns the write policy gate. See [03](./03-write-path.md). |
| **`RetrievalLog`** | Append-only record of every read | One row per alert per run, including empty retrievals. Feeds Phase 4 metrics. |

`CaseRenderer` is deliberately shared by `Retriever` and `Writer`. It is the mechanism that enforces query/document symmetry — if there were two renderers, they would drift.

---

## The `MemoryLayer` interface

The shared-code constraint ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §9) is enforced by making the memory layer a **single interface with two implementations**, selected by config. The triage loop calls the same methods in both arms and contains **no arm conditionals**.

```python
class MemoryLayer(Protocol):
    def retrieve(self, alert: Alert) -> RetrievalResult: ...
    def write(self, case: TriagedCase) -> WriteResult: ...
```

- **`ChromaMemoryLayer`** — the real implementation. Used in Arm B.
- **`NullMemoryLayer`** — returns an empty `RetrievalResult` and a no-op `WriteResult`. Used in Arm A.

The triage loop is therefore literally identical across arms:

```python
retrieval = memory.retrieve(alert)          # Arm A: always empty
prompt    = PROMPT_TEMPLATE.render(alert, retrieval.cases)   # empty list → no precedent block
verdict   = llm.triage(prompt)              # same wrapper, same model, same params
memory.write(TriagedCase(alert, verdict))   # Arm A: no-op
retrieval_log.append(alert.id, retrieval)   # Arm A: logs an empty retrieval
```

[`CLAUDE.md`](../../CLAUDE.md) states the rule directly: if an `if arm == "baseline"` branch appears anywhere outside the memory module, the design is wrong and must be raised rather than worked around. The only place the arm is named is the config that picks the implementation.

### Consequences to preserve

- **The prompt template is one object.** It must render cleanly with zero precedent cases and produce exactly the Arm A prompt. Verify with a test asserting the Arm A rendered prompt is byte-identical to the same template rendered with an empty case list. If the template emits an empty "Relevant past cases:" header in Arm A, the arms differ by a prompt and the control is broken. The base prompt template is a **protected component** — identical across arms, no per-arm wording.
- **`NullMemoryLayer` must not load the embedding model.** Arm A should incur no embedding cost. This matters for the latency-overhead metric — that metric measures the memory layer's cost, so Arm A must carry none of it.

### Verifying the baseline never writes

[`CLAUDE.md`](../../CLAUDE.md) requires this be *verified before any baseline run*, not assumed. Three checks, all cheap:

1. **Unit** — `NullMemoryLayer.write()` is asserted to perform no I/O and hold no store handle.
2. **Startup** — an Arm A run asserts `memory.enabled == false` and that no store path was opened.
3. **Post-run** — an Arm A run's manifest records zero writes and zero embedding calls. A non-zero count fails the run.

An Arm A run whose configuration could reach a live store is not a valid baseline, regardless of whether it actually wrote anything.

---

## Read path sequence

```
Alert
  │
  ├─► CaseRenderer.to_query_text(alert)      ── same template as write, verdict fields omitted
  │
  ├─► EmbeddingFunction.encode(text)         ── L2-normalized
  │
  ├─► collection.query(n_results=k, where=filter)
  │
  ├─► distance → similarity  (cosine: sim = 1 - distance)
  │
  ├─► drop cases with sim < threshold
  │
  ├─► RetrievalLog.append(all candidates, distances, survivors)
  │
  └─► RetrievalResult(cases=[...])           ── possibly empty
```

An empty result is a normal outcome, not an error. It is the expected state during cold start and the correct state when nothing relevant exists. Detail in [04 — Read path](./04-read-path.md).

## Write path sequence

```
TriagedCase (alert + verdict + rationale + confidence)
  │
  ├─► WritePolicy.should_write(case)         ── returns bool + reason
  │       └─ rejected? log the rejection and stop. Rejections are data.
  │
  ├─► CaseRenderer.to_document(case)         ── embedding text + metadata dict
  │
  ├─► EmbeddingFunction.encode(text)
  │
  └─► collection.add(ids=[case_id], embeddings=[...], documents=[...], metadatas=[...])
```

Write happens **after** the verdict is produced and **after** it has been logged for scoring, so a write failure cannot corrupt the evaluation record. Detail in [03 — Write path](./03-write-path.md).

---

## Ordering guarantee

The write for alert *n* must complete before the read for alert *n+1* begins. The memory layer's entire premise is that precedent accumulates in stream order; concurrent or batched writes would make the retrievable state at alert *n* depend on scheduling, and the run would not be reproducible.

**Process the stream strictly sequentially.** If throughput ever becomes a problem, the fix is a faster embedding model — subject to the protected-component rule — not parallelism.

---

## Store lifecycle and reproducibility

The store is stateful, and that state is an *output* of a run as much as the verdicts are. This creates a reproducibility hazard that does not exist in Arm A.

**The hazard:** run Arm B, then run it again. The second run starts with a fully populated store, so alert #1 now retrieves precedent it could not possibly have had the first time. The two runs are not comparable, and neither is comparable to Arm A.

**The obvious fix is forbidden.** Clearing the collection between runs would be the natural solution, but the case store is a **protected component**: [`CLAUDE.md`](../../CLAUDE.md) states it must never be deleted, wiped, or regenerated without explicit instruction, and separately forbids destructive operations such as DB drops. An automated `reset()` that drops the collection at the start of every run violates both.

### Resolution: create, never destroy

A run does not clear a store — it **creates a new one**.

- Every run persists to its own directory, `data/memory/<run_id>/`. A `run_id` is unique per run.
- A fresh directory *is* an empty store. No deletion is involved, so the invariant holds by construction rather than by discipline.
- If `data/memory/<run_id>/` already exists, the run **aborts**. It does not overwrite, merge, or clear. A colliding `run_id` is an operator error, and the safe response is to stop.
- Old run stores accumulate on disk. **Removing them is a human decision, made explicitly** — never an automated step, never a side effect of starting a run.

This is a better design than reset-on-start regardless of the rule: every run's memory is a durable, inspectable artifact that can be archived with its results, and no run can destroy the evidence of another.

### Declared initial state

| State | Meaning | Used for |
|---|---|---|
| `empty` | A new, never-before-used run directory. | The default for a scored Arm B run — models a genuine cold start. |
| `seeded:<snapshot-id>` | A snapshot **copied into** the new run directory before the run starts. | Warm-start experiments. Snapshot provenance must be documented — see [OQ-4](./07-open-questions.md#oq-4--where-does-a-cold-start-seed-set-come-from). |

Seeding copies *into* a fresh directory. The snapshot itself is read-only and is never modified by the run that consumes it.

### Recorded per run

- `initial_state`, and for `seeded:`, the snapshot ID and its provenance.
- Collection count at run start and run end.
- A content hash over all case IDs at run end.

These go in the run manifest. [`CLAUDE.md`](../../CLAUDE.md) requires every run be reproducible with fixed seeds, logged config, and recorded model versions; for this layer, the store's start and end state is part of that record.

---

## What this layer does *not* do

Stated explicitly because each of these is a tempting scope creep that would contaminate the experiment:

- **It does not decide.** Retrieved precedent is context handed to the LLM. The memory layer never overrides, short-circuits, or vetoes a verdict. A "if similarity > 0.98, reuse the past verdict directly" shortcut would be a *different system* — it would bypass the LLM and make the comparison meaningless.
- **It does not re-rank with a second model.** Ranking is cosine similarity on the fixed embedding model, plus a threshold. A cross-encoder reranker is a second variable.
- **It does not mutate stored cases.** No updates to past verdicts when a later case contradicts them. Memory is append-only. Retroactive correction is a plausible future feature and an explicit non-goal here — it would confound error propagation, which is the failure mode this project exists to measure.
- **It does not summarize or compress.** Cases are stored as rendered, not as LLM-generated summaries. A summarization step would insert a second LLM call into the memory layer and make it non-deterministic.
- **It does not touch Layer 2.** Detector outputs are consumed as given. Detector weights and thresholds are frozen, and nothing in this layer may feed back into them.
