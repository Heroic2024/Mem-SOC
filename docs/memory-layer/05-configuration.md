# 05 — Configuration & Operations

> ChromaDB and embedding-model setup for the memory layer. Implements [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §6 and the Phase 0 setup task in §7.

---

## Dependencies

[`CLAUDE.md`](../../CLAUDE.md) requires that any new dependency be justified with what, why, and the lighter alternative rejected, and that the standard library be preferred. This layer needs exactly two beyond the standard library:

| Dependency | Why | Lighter alternative rejected |
|---|---|---|
| `chromadb` | The vector store. Named in [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §6 as a settled technology choice — Apache 2.0, on-disk persistence, per-entry metadata filtering, HNSW top-k. | A hand-rolled NumPy brute-force index over a JSONL store. Genuinely viable at this scale and dependency-free, but it would reimplement metadata filtering and persistence, and §6 has already settled this. |
| `sentence-transformers` | The embedding model. Named in §6. | Loading the checkpoint through `transformers` directly and pooling manually. Fewer transitive packages, but hand-rolled pooling and normalization is exactly where the read/write asymmetry bug in [R4](./06-risks-and-limitations.md#r4--embedding-model-mismatch) would hide. |

Anything further — rerankers, alternate index backends, embedding caches — is a new variable as well as a new dependency. Raise it before adding it.

---

## Version pinning

Pin exact versions. Not ranges.

```
chromadb==<pin>
sentence-transformers==<pin>
torch==<pin>
```

This is not general hygiene — it is an experimental-control requirement. A `chromadb` minor upgrade can change HNSW defaults, and a `sentence-transformers` upgrade can change pooling or normalization behaviour. Either would silently alter the embedding space between Arm A's run and Arm B's run, and the comparison would be measuring a library upgrade.

Record the resolved versions in every run manifest, read at runtime from the installed packages rather than transcribed from the lockfile. [`CLAUDE.md`](../../CLAUDE.md) requires recorded model versions for every run, and separately forbids modifying dependency lockfiles as a side effect of a feature task.

> **API drift warning.** ChromaDB's collection-configuration API changed across the 0.4 → 0.5 → 1.x line, particularly how the HNSW distance space is specified (`metadata={"hnsw:space": ...}` in older versions versus a structured `configuration=` argument in newer ones). Verify the correct form against the installed version's own documentation before writing the collection-creation code, and assert the resolved space after creation rather than trusting that the argument was accepted — an unrecognized key can be silently ignored, leaving you on the L2 default with cosine thresholds. See [§Distance space](#distance-space).

---

## Embedding model

**The embedding model is a protected component.** [`CLAUDE.md`](../../CLAUDE.md): *never swap or change versions; same model on write and read paths, always.*

The practical consequence is that **the choice must be made, measured, and justified in Phase 0** — before Phase 2 locks the embedding function ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 Phase 2). After that point, discovering the model is a poor fit is not something that can be quietly fixed; it requires explicit approval and a full re-render of every stored case into a new store. Do the measurement first. See [OQ-8](./07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2).

**Candidate named in [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §6:** `sentence-transformers/all-MiniLM-L6-v2`.

| Property | Value |
|---|---|
| Output dimensions | 384 |
| Max sequence length | **256 word-piece tokens** |
| Runs locally | Yes — no API dependency, no per-call cost, no network variance |
| Normalization | Enable explicitly (`normalize_embeddings=True`) |

### Token budget

The sequence-length limit is the constraint that most directly threatens correctness, because **exceeding it fails silently.** The tokenizer truncates and the model returns a perfectly valid-looking vector computed from partial text. Nothing raises.

The template in [02](./02-case-schema.md#template--draft-pending-oq-9) is sized to land around 120–160 tokens, but addresses and long float strings tokenize poorly and inflate the count unpredictably — and the final field list is still pending the Layer 2 contract ([OQ-9](./07-open-questions.md#oq-9--what-does-layer-2-emit)).

**Required in Phase 0, before the model is locked:** render a large sample of cases under the final template, tokenize each, and report the token-length distribution. If the p99 approaches the limit, resolve it *now* — by trimming the template or by choosing a different model — rather than after the lock.

Add an assertion in `CaseRenderer` that raises when a rendered case exceeds the model's limit, so truncation can never happen unnoticed mid-run.

### Determinism

Embeddings must be reproducible across runs on the same machine.

- Load the model **once** per process and share the instance across read and write. This is Invariant #1 made structural — two instances are two opportunities to diverge.
- Set the model to eval mode and disable gradients.
- Pin the device explicitly (`cpu` or `cuda`) and record it in the manifest. CPU and GPU produce slightly different floating-point results; the differences are tiny but they move borderline cases across a similarity threshold.
- Verify: embed the same text twice, assert exact equality. Then embed a fixed corpus at run start and compare its hash against a stored reference — this catches a model or library change that nothing else would surface.

---

## ChromaDB

### Client

Persistent, on-disk, from day one ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4 Layer 3; [`CLAUDE.md`](../../CLAUDE.md) Code & Repo Rules — *persistent/on-disk mode for the vector store, always; never in-memory*). No `EphemeralClient`, not even for tests that assert persistence behaviour.

```python
client = chromadb.PersistentClient(path=f"artifacts/memory/{run_id}")
```

**Run-scoped path.** A shared global path lets one run's state leak into the next, which breaks the identical-sequence guarantee, and it is what forces destructive resets. Each run owns its directory; the directory *is* the run's memory artifact and can be archived with the results. See [01 §Store lifecycle](./01-architecture.md#store-lifecycle-and-reproducibility).

**The store directory is not committed.** [`CLAUDE.md`](../../CLAUDE.md) forbids committing data files, model weights, `.env` files, API keys, or the vector store directory. It also forbids modifying `.gitignore` as a side effect of a feature task — so if `data/` is not currently ignored, raise it as its own change rather than folding it into memory-layer work.

### Collection

One collection: `soc_cases`. Not one per attack type, not one per day — partitioning would build a label-shaped prior into the store's structure and let retrieval succeed for reasons other than similarity.

Configure at creation:

- **Distance space: cosine.** Explicitly, not by default.
- **Embeddings supplied by the caller.** Do not attach an embedding function to the collection; the write path passes vectors it computed with the shared model. This keeps the one-model invariant visible in code rather than buried in collection config.

### Distance space

The default space is **L2**, and cosine must be requested explicitly. Getting this wrong is quiet and expensive: a `τ_read` of 0.7 means something under cosine and something entirely different under L2, and nothing will error.

**Assert it after creation.** Read the space back from the collection's configuration and fail the run if it is not cosine. If the installed version makes the configured space awkward to read back, use a behavioural check instead: add two known vectors, query, and verify the returned distance matches `1 - cos_sim` to within floating-point tolerance. Run this at startup, every run.

### HNSW parameters

Leave at defaults. HNSW construction and search parameters (`ef_construction`, `M`, `ef_search`) trade recall against speed, and tuning them would make retrieval quality a second variable alongside the memory layer itself. At this project's scale — thousands to low tens of thousands of vectors — defaults give effectively exact recall.

If they are ever changed, they become part of the reported configuration.

---

## Configuration surface

One object, one source of truth, serialized into every run manifest:

```yaml
memory:
  enabled: true                      # false ⇒ NullMemoryLayer ⇒ Arm A
  store:
    path: artifacts/memory/{run_id}
    collection: soc_cases
    distance: cosine
    initial_state: empty             # or seeded:<snapshot-id>
  embedding:
    model: sentence-transformers/all-MiniLM-L6-v2   # locked in Phase 0 — see OQ-8
    dimensions: 384
    max_seq_length: 256
    normalize: true
    device: cpu
  schema_version: "1.0"
  read:
    top_k: 5
    threshold: 0.7                   # τ_read, cosine similarity
    where_filter: null
    diversity: off
    max_precedent_tokens: 1200
  write:
    policy: write_all                # write_all | confidence_gated | confirmed_only
    confidence_threshold: null       # required iff policy == confidence_gated
```

`memory.enabled` is the **only** arm switch in the system. Nothing else in the codebase branches on arm ([01 §The MemoryLayer interface](./01-architecture.md#the-memorylayer-interface)).

Two properties this must have:

- **Fully serialized into the manifest**, including resolved defaults — not just the values that were overridden. A parameter that was never written down cannot be reproduced.
- **Validated at startup**, before any alert is processed: `confidence_threshold` present iff the policy needs it, `threshold` in [0, 1], `top_k` ≥ 1, `dimensions` matching what the model actually returns when probed. Fail fast; a misconfiguration discovered at alert 4,000 costs the whole run.

---

## Operations

Behaviours the harness needs. Names are illustrative; the requirement is that each is a callable operation rather than a manual procedure.

Note what is **absent**: there is no wipe, no drop, and no regenerate. The case store is a protected component ([`CLAUDE.md`](../../CLAUDE.md) — *never delete, wipe, or regenerate without explicit instruction*), and [`CLAUDE.md`](../../CLAUDE.md) separately forbids destructive commands such as DB drops without explicit instruction. A fresh store is obtained by creating a new run directory, never by clearing an old one.

| Operation | Purpose |
|---|---|
| `create(run_id)` | Create `artifacts/memory/<run_id>/` and its collection. **Aborts if the directory already exists** — never overwrites, merges, or clears. |
| `snapshot(tag)` | Copy a run's store directory to `data/snapshots/<tag>/`, recording run ID, sequence position, and case count. Read-only thereafter. |
| `seed(run_id, tag)` | Copy a snapshot *into* a new run directory before the run starts. Sets `initial_state: seeded:<tag>`. |
| `inspect(run_id)` | Report count, `schema_version`, verdict distribution, detector-label distribution, date range. First stop when results look wrong. |
| `verify(run_id)` | Assert: single `schema_version`; distance space is cosine; embedding dimensions match config; no duplicate `case_id`s; every case in Chroma has a sidecar row and vice versa. |
| `export(run_id)` | Dump all cases with metadata to JSONL for offline analysis, so analysis never needs a live Chroma handle. |

Retiring an old run store is a **human decision, taken explicitly** — not an automated step and not a side effect of starting a run.

`verify` should run at the end of every scored run and its result recorded in the manifest. A run that fails verification is not reportable.

---

## Startup checklist

Executed before the first alert of any Arm B run, with failures aborting the run:

1. Resolved package versions recorded in the manifest.
2. Embedding model loaded; probe text embedded; dimensions match config.
3. Determinism check: same text embedded twice, exact match.
4. Reference-corpus hash matches the stored reference (detects a silent model/library change).
5. Store path is run-scoped and does not already exist; it is created fresh. For `seeded:`, the snapshot is copied in and its tag recorded.
6. Collection distance space verified as cosine, behaviourally.
7. `schema_version` in config matches any version already present in the collection.
8. Config validated; full resolved config serialized to the manifest.

Arm A runs skip 2–7 entirely. `NullMemoryLayer` loads no model and opens no store — that is what makes its zero latency overhead real rather than reported ([04 §Latency and token accounting](./04-read-path.md#latency-and-token-accounting)), and it is part of the pre-run verification that the baseline cannot write ([01](./01-architecture.md#verifying-the-baseline-never-writes)).
