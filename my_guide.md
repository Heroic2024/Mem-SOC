# How an Alert Becomes a Stored Case — A Walkthrough

The full journey of one alert, end to end, using the illustrative example from `docs/memory-layer/02-case-schema.md` so you can follow a single case the whole way through.

---

## The big picture

The vector DB does not store the ML model's output directly. It stores a **case** — the alert plus what the LLM concluded about it. And the thing that actually gets searched is not the numbers at all; it's an English-ish sentence built from those numbers.

```
alert ──► [2] ML detector ──► [3] READ memory ──► [4] LLM triage ──► [3] WRITE memory
                                     ↑                                        │
                                     └────────────────────────────────────────┘
```

The memory layer is touched **twice per alert**: once to read (before the LLM thinks), once to write (after it decides). Storing is the second half. (`docs/memory-layer/01-architecture.md:17`)

---

## Step 0 — What arrives from the ML model

One flow record comes in from Layer 1 (a row of NF-* v3 NetFlow features). The detector looks at it and emits three things the memory layer needs:

| What the detector gives | Becomes |
|---|---|
| A predicted label | `detector_label` |
| A confidence/score for that label | `detector_score` |
| Its own version string | `detector_version` |

⚠️ **This contract is not settled yet.** The detector hasn't been chosen — that's a Phase 0 task, and it's why `docs/memory-layer/02-case-schema.md:23` calls this "The Layer 2 input contract" instead of naming fields. In particular, **if the chosen detector only outputs a class and no score, part of this design breaks** (the score is rendered into the searchable text *and* it's what the `confidence_gated` write policy gates on). Everything below marked *pending* is waiting on that decision — see OQ-9.

Nothing is stored at this point. The detector output is just carried forward.

---

## Step 1 — The LLM triages, and only *then* do we store

Before storing, the alert has already been through retrieval and the LLM. The verdict comes back with four things: `verdict`, `attack_category`, `confidence`, and a written rationale.

**Order matters, and it's deliberate** (`docs/memory-layer/03-write-path.md:11`):

```
verdict produced
  → verdict written to the SCORING log      ← the evaluation record is now safe
  → then, and only then, consider storing it in memory
```

Why: if the vector DB write blows up mid-run, you must not lose a verdict from your results. The experiment's scorecard can never depend on the memory layer working.

---

## Step 2 — The gatekeeper: should this be stored at all?

A `WritePolicy` gets asked `should_write(case)` → returns yes/no plus a reason. Three options exist (`docs/memory-layer/03-write-path.md:42`):

- **`write_all`** — store everything, right or wrong. This is the recommended default, because errors landing in memory is *the phenomenon the project exists to measure*. Filtering them out would hide the result.
- **`confidence_gated`** — store only if confidence ≥ some floor. Reduces bad precedent but does **not** eliminate it: a confidently wrong LLM verdict sails straight through.
- **`confirmed_only`** — store only ground-truth-confirmed cases. Effectively unusable as a headline config, because the only confirmation source here is the dataset's answer key, which turns memory into a cheat sheet.

**If the policy says no, the case is still recorded** in the sidecar file with the rejection reason. Knowing what memory *refused* to learn is a data point.

---

## Step 3 — The case gets split three ways

This is the core idea. One case is not one blob; it goes to three places with three different jobs (`docs/memory-layer/02-case-schema.md:13`):

| Part | Where | Job |
|---|---|---|
| **Embedding text** | Chroma `documents` | Decides *what "similar" means* |
| **Metadata** | Chroma `metadatas` | Decides *what you can filter on and cite* |
| **Sidecar record** | a plain `cases.jsonl` file | Everything bulky: full rationale, full feature vector, audit trail |

The rule to hold onto: **only what's in the embedding text affects matching.** Metadata is retrievable and filterable but completely invisible to similarity search. Anything in the sidecar isn't in the database at all — it's joined back later by `case_id`.

---

## Step 4 — Render the numbers into text

`CaseRenderer` takes the flow features and formats them into a fixed 9-line template (`docs/memory-layer/02-case-schema.md:70`):

```
ALERT Wednesday 2017-07-05T09:12:44
172.16.0.1:54312 -> 192.168.10.50:80 TCP port http
Detector: <label> score 0.91
Volume: 8 fwd / 6 bwd pkts, 1892 / 11640 bytes
Rate: 412 pkt/s, 1094320 B/s over 34 ms
Size: fwd mean 236 max 1024, bwd mean 1940 max 2896
Timing: IAT mean 2615 std 4102, idle mean 0
Flags: SYN 0 FIN 0 RST 0 PSH 1 ACK 1 URG 0
Shape: down/up 6, avg pkt 966, init win 29200/235
```

**Why only a subset and not all 48 features?** Three reasons (`docs/memory-layer/02-case-schema.md:60`): the embedding model truncates at 256 tokens and silently drops whatever doesn't fit; long numeric strings all compress toward each other so more numbers ≠ more signal; and many NF-* v3 columns are near-duplicates of each other anyway.

**Why these rules matter more than they look:**
- `6` → `TCP` and `80` → `http`, because `ssh` means something to a language model and `22` doesn't.
- Fixed decimal precision — `1523.4471028` and `1523.4` produce different vectors.
- Every line always present, same order. A missing line shifts everything after it.
- `NaN`/`Inf` render as the literal `n/a`. The NF-* v3 rate/throughput columns have non-finite or missing values for zero-duration flows.

**The symmetry rule** (`docs/memory-layer/02-case-schema.md:48`): the *same renderer object* is used on the read path. When searching, we describe the incoming alert with this exact template. If writing used a template with a `VERDICT:` line and reading used one without, queries and documents would sit in different regions of the space and similarity would quietly degrade. That's why `CaseRenderer` is one shared class, not two — there's no opportunity for them to drift.

Note the verdict is deliberately **not** in the embedding text. Retrieval semantics we want is "find alerts that look like this one," not "find alerts with this conclusion." (This is OQ-1 — the brief is internally inconsistent on it and it needs a team decision.)

---

## Step 5 — Turn the text into a vector

```
EmbeddingFunction.encode(text) → [0.0231, -0.1847, ..., 0.0912]   # 384 numbers
```

The candidate model is `all-MiniLM-L6-v2`: 384 dimensions, normalized to unit length so cosine similarity works cleanly.

Three non-negotiables here:

1. **One model instance per process, shared by read and write.** Not "the same model name" — literally the same loaded object. Different models, versions, or normalization settings between the two paths make similarity *meaningless while still returning results that look fine*. Nothing errors. That's R4, and it's the nastiest bug in this layer.
2. **The model is frozen** once locked. It can never be swapped later, which is why its selection has to be measured in Phase 0 rather than fixed mid-project (OQ-8).
3. **Token-length assertion.** `CaseRenderer` raises if a rendered case exceeds 256 tokens, so truncation can't happen unnoticed.

---

## Step 6 — Build the metadata dict

Small, flat, filterable. Chroma only accepts `str`, `int`, `float`, `bool` — no `None`, no lists, no nesting (`docs/memory-layer/02-case-schema.md:106`).

```json
{
  "case_id": "r7f3a1:000412", "run_id": "r7f3a1", "seq": 412,
  "alert_id": "r7f3a1:000412",
  "created_at": "2026-07-31T11:54:03Z", "schema_version": "1.0",

  "src_ip": "172.16.0.1", "src_port": 54312,
  "dst_ip": "192.168.10.50", "dst_port": 80,
  "protocol": 6, "protocol_name": "TCP",
  "day": "Wednesday", "timestamp": "2017-07-05T09:12:44",

  "detector_label": "<pending>", "detector_score": 0.91, "detector_version": "<pending>",

  "verdict": "true_positive", "attack_category": "<pending>", "confidence": 0.88,
  "rationale_summary": "High bytes/s with sustained ACK-PSH exchange to port 80...",
  "precedent_used": "r7f3a1:000097,r7f3a1:000201", "precedent_count": 2
}
```

Four things worth calling out:

- **`case_id` = `{run_id}:{seq:06d}`** — not a random UUID. It's sortable, and it tells you exactly which run and which stream position produced it. A case ID you can't trace back to a position in the stream isn't citable in an audit.
- **`precedent_used`** — the case IDs that informed *this* verdict. This is what makes error propagation traceable: it turns the store into a graph where you can follow a wrong verdict forward and see exactly which later cases it infected. Comma-joined because Chroma won't take lists.
- **Time fields must never be used as a filter.** In testbed captures each attack family sits in specific capture windows, so filtering by time leaks the answer through the filter. Store for analysis, never for retrieval.
- **There is no `ground_truth` field, on purpose.** The true labels are the grading key. Put them in memory and memory becomes an oracle instead of an analyst's notebook, which would inflate Arm B's results into meaninglessness. (Still formally open as OQ-2 — the absence is the working assumption, not a settled decision.)

---

## Step 7 — The actual write

Two things happen:

```python
collection.add(
    ids        = ["r7f3a1:000412"],
    embeddings = [[0.0231, -0.1847, ...]],   # computed by US, passed in explicitly
    documents  = ["ALERT Wednesday 2017-07-05T09:12:44\n172.16.0.1:54312 -> ..."],
    metadatas  = [{...}],
)
```

...plus one line appended to `data/memory/<run_id>/cases.jsonl` holding the heavy stuff: full untruncated rationale, both report views, the complete feature vector as ingested, every retrieval candidate with its distance, token counts, latency.

**Why pass embeddings in rather than letting Chroma compute them?** Because then the shared-model rule is visible in the code instead of hidden in collection config. (`docs/memory-layer/03-write-path.md:38`)

**Why the sidecar split?** Chroma loads metadata into RAM with the collection. Multi-kilobyte rationales as metadata bloat the resident footprint for data you never filter on. Nothing is lost — you join on `case_id`.

Under the hood Chroma inserts the vector into an HNSW index (cosine space, explicitly configured — the default is L2, and a threshold tuned for one is nonsense under the other) and flushes to disk.

---

## Step 8 — Log the write

```json
{"seq": 412, "case_id": "r7f3a1:000412", "written": true,
 "policy": "write_all", "reason": "write_all",
 "embed_ms": 8.4, "add_ms": 2.1, "collection_count_after": 388}
```

`collection_count_after` is the important one — it tells you exactly how big memory was at every point in the stream, which is the only way to separate cold-start performance from steady-state performance in Phase 4. You cannot reconstruct it afterwards.

---

## Where it all lands

```
data/memory/r7f3a1/
├── chroma.sqlite3          ← vectors, documents, metadata (Chroma's own files)
├── <uuid>/                 ← the HNSW index
├── cases.jsonl             ← sidecar: the bulky stuff
└── writes.jsonl            ← the write log above
```

**One directory per run, and it is never deleted.** A fresh directory *is* an empty store, so "reset memory before a run" is achieved by creating rather than destroying. If the directory already exists, the run aborts rather than overwriting or merging (`docs/memory-layer/01-architecture.md:141`). This satisfies the protected-component rule on the case store, and it also means every run's memory is a durable artifact you can archive alongside its results.

---

## Two things that are easy to miss

**Arm A writes nothing.** `NullMemoryLayer.write()` returns immediately — no rendering, no embedding, no disk. It doesn't even load the embedding model, which is what makes its "zero overhead" real rather than merely reported. This is verified before every baseline run, not assumed.

**The store is append-only.** No case is ever updated. If alert #900 proves that alert #97's verdict was wrong, #97 stays wrong in memory. That's not laziness — retroactively correcting memory would erase exactly the error-propagation dynamic the project is trying to measure.

---

## What's still undecided before any of this can be built

| # | Question |
|---|---|
| OQ-9 | What does the detector actually emit? Blocks most of the schema. |
| OQ-1 | Does the embedded text include the verdict? |
| OQ-2 | Does ground truth ever touch the store? (Reserved — not to be implemented either way without confirmation.) |
| OQ-3 | Where does `attack_category` come from? |
| OQ-8 | Which embedding model gets locked? |

`docs/memory-layer/02-case-schema.md` is explicitly labelled a **proposal**, and every field inherited from the detector is marked **pending** rather than guessed at.
