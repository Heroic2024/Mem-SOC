# ChromaDB Setup Guide — Memory Layer (Layer 3)

> Hands-on companion to [`docs/memory-layer/05-configuration.md`](docs/memory-layer/05-configuration.md). That doc says *what* the configuration must be and *why*; this doc is the sequence of commands to actually stand it up and verify it. Read both — this one will not repeat the reasoning, only point at it.
>
> Scope: Phase 0 of [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) §7 — *"Install ChromaDB and embedding model. Persistent mode from the start."* It stops at a verified, empty, correctly-configured store. It does **not** implement `CaseRenderer`, the read path, or the write path — those depend on the case schema, which is still a proposal pending [OQ-9](docs/memory-layer/07-open-questions.md#oq-9--what-does-layer-2-emit) and other open questions. Do not treat anything below as a schema or design decision.

---

## 0. Before you start

| Check | Why |
|---|---|
| Python available (`python --version`) | This environment has Python 3.13.2 on the shell used to write this guide — confirm yours. |
| No `chromadb` / `sentence-transformers` currently installed (`pip show chromadb`) | Confirms you're starting clean, not fighting a stale install. |
| You are **not** about to touch `data/`, `.gitignore`, or any file under `docs/memory-layer/` | Out of scope for this guide. `data/` not being in `.gitignore` yet is a real gap — raise it separately, don't fix it as a side effect ([`CLAUDE.md`](CLAUDE.md)). |

---

## 1. Install the two dependencies

Per [`docs/memory-layer/05-configuration.md`](docs/memory-layer/05-configuration.md#dependencies), exactly two packages are justified beyond the standard library: `chromadb` (the vector store) and `sentence-transformers` (the embedding model, which pulls in `torch`). Nothing else — a reranker, an alternate index, an embedding cache — without raising it first.

```bash
pip install chromadb sentence-transformers torch
```

On Windows with no GPU, `pip` resolves the CPU build of `torch` by default — that's correct here, since the locked device is `cpu` ([05 §Configuration surface](docs/memory-layer/05-configuration.md#configuration-surface)). You don't need `--index-url` tricks unless you specifically want CUDA.

### Pin what actually resolved

Don't hand-write version numbers into a requirements file before installing — record what `pip` actually resolved:

```bash
pip freeze | findstr /I "chromadb sentence-transformers torch"
```

(`grep -i` on macOS/Linux.) Copy those three exact lines somewhere durable (a `requirements.txt` for the memory layer, once one exists — creating it is a separate, deliberate step, not part of this guide). This matters more than routine hygiene: a `chromadb` minor version can change HNSW defaults, and a `sentence-transformers` upgrade can change pooling/normalization — either would silently shift the embedding space between an Arm A and Arm B run. See [05 §Version pinning](docs/memory-layer/05-configuration.md#version-pinning).

---

## 2. Check which ChromaDB API you actually have

[05 §Version pinning](docs/memory-layer/05-configuration.md#version-pinning) calls this out explicitly: the collection-configuration API — especially how you specify the HNSW distance space — changed across the 0.4 → 0.5 → 1.x line. Find out which you have before writing any collection-creation code:

```bash
python -c "import chromadb; print(chromadb.__version__)"
```

Then check that version's own changelog/docs for whether collection creation takes `metadata={"hnsw:space": "cosine"}` (older) or a structured `configuration=` argument (newer). Don't assume — the guide below shows the pattern, but the exact call shape is a fact about the installed package, not something to copy blindly.

---

## 3. Create the persistent client

Never `EphemeralClient`, not even for a throwaway test — persistent, on-disk, from the first line of code ([`CLAUDE.md`](CLAUDE.md); [05 §Client](docs/memory-layer/05-configuration.md#client)):

```python
import chromadb

run_id = "smoketest-0001"   # a real run_id scheme comes later; anything unique is fine here
client = chromadb.PersistentClient(path=f"artifacts/memory/{run_id}")
```

Each run gets its **own directory** — never a shared global path. If `artifacts/memory/<run_id>/` already exists, that's a collision; the correct response is to pick a new `run_id`, not to reuse or clear the old one ([01 §Store lifecycle](docs/memory-layer/01-architecture.md#store-lifecycle-and-reproducibility)). There is no `reset()` operation in this design — a fresh store is a fresh directory, not a wiped one.

---

## 4. Create the collection with cosine space — and verify it

One collection, named `soc_cases` ([05 §Collection](docs/memory-layer/05-configuration.md#collection)). The default distance space in Chroma is **L2**; cosine must be requested explicitly, and getting this wrong fails silently — no error, just thresholds that mean something different than you think.

```python
collection = client.create_collection(
    name="soc_cases",
    metadata={"hnsw:space": "cosine"},   # verify this is the right form for your installed version — see step 2
)
```

**Then verify it actually took**, behaviourally rather than by trusting the argument was accepted ([05 §Distance space](docs/memory-layer/05-configuration.md#distance-space)):

```python
import numpy as np

# two known unit vectors with a known cosine similarity
v1 = [1.0, 0.0]
v2 = [0.0, 1.0]  # orthogonal -> cosine similarity 0.0 -> expected distance 1.0

collection.add(ids=["probe-1", "probe-2"], embeddings=[v1, v2], documents=["a", "b"])
result = collection.query(query_embeddings=[v1], n_results=2)
print(result["distances"])   # expect [0.0, ~1.0] under cosine; something else under L2

collection.delete(ids=["probe-1", "probe-2"])   # clean up the probe vectors
```

If the returned distance for the orthogonal pair isn't ~1.0, the space did not get configured as cosine — stop and fix it before going further. This check belongs in a startup routine eventually ([05 §Startup checklist](docs/memory-layer/05-configuration.md#startup-checklist), item 6), not just a one-off here.

Leave HNSW construction/search parameters (`ef_construction`, `M`, `ef_search`) at their defaults — tuning them makes retrieval quality a second variable alongside the memory layer itself ([05 §HNSW parameters](docs/memory-layer/05-configuration.md#hnsw-parameters)).

---

## 5. Load the embedding model and verify determinism

**The embedding model is a protected component** — never swapped after it's locked, and the same loaded instance must be used on both the read and write paths ([`CLAUDE.md`](CLAUDE.md); [01 §Components](docs/memory-layer/01-architecture.md#components)). The candidate named in [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) §6 is `sentence-transformers/all-MiniLM-L6-v2` — but it is **not locked yet**. [OQ-8](docs/memory-layer/07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2) requires measuring the rendered case template's token-length distribution against the model's 256-token limit *before* it's locked. This step is about getting the model running and verified, not about locking it.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
model.eval()

def embed(text: str):
    return model.encode(text, normalize_embeddings=True).tolist()
```

Load it **once** per process and share the instance across anything that reads and anything that writes — two instances are two opportunities for read/write drift ([05 §Determinism](docs/memory-layer/05-configuration.md#determinism)).

Verify determinism before trusting it:

```python
text = "ALERT probe 2026-08-08T00:00:00\n10.0.0.1:1234 -> 10.0.0.2:80 TCP port http"

e1 = embed(text)
e2 = embed(text)
assert e1 == e2, "same text embedded twice must be exactly equal"
print("dims:", len(e1))   # expect 384 for MiniLM
```

If this assertion fails, stop — nothing downstream (thresholds, retrieval) is trustworthy until embeddings are reproducible on this machine.

---

## 6. End-to-end smoke test

Confirm the full write → query → similarity round-trip works before building anything on top of it:

```python
case_text = "ALERT Wednesday 2017-07-05T09:12:44\n172.16.0.1:54312 -> 192.168.10.50:80 TCP port http"
vec = embed(case_text)

collection.add(
    ids=["smoke-0001"],
    embeddings=[vec],
    documents=[case_text],
    metadatas=[{"case_id": "smoke-0001", "note": "setup smoke test"}],
)

query_vec = embed("ALERT Wednesday 2017-07-05T09:15:02\n172.16.0.1:54400 -> 192.168.10.50:80 TCP port http")
result = collection.query(query_embeddings=[query_vec], n_results=1, include=["documents", "metadatas", "distances"])

distance = result["distances"][0][0]
similarity = 1 - distance   # cosine space only — see 04-read-path.md
print(f"distance={distance:.4f} similarity={similarity:.4f}")

collection.delete(ids=["smoke-0001"])   # this was a smoke test, not real memory — clean it up
```

A similar, related-looking alert should come back with a high similarity (roughly 0.8+, though don't over-index on the exact number from two hand-written strings). If it comes back near zero or negative, something upstream is wrong — most likely the distance space.

Delete the probe/smoke-test directory afterward too (`artifacts/memory/smoketest-0001/`) — it isn't a real run and has no reason to persist:

```bash
rmdir /s /q data\memory\smoketest-0001
```

---

## 7. What this guide deliberately does not do

- **Does not implement `CaseRenderer`, the write path, or the read path.** Those require the case schema, which is a proposal pending several open questions ([OQ-1](docs/memory-layer/07-open-questions.md#oq-1--does-the-embedded-text-include-the-verdict), [OQ-9](docs/memory-layer/07-open-questions.md#oq-9--what-does-layer-2-emit)). Building against an unlocked schema means rebuilding it later.
- **Does not lock the embedding model.** That requires the token-length measurement in [OQ-8](docs/memory-layer/07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2), which in turn needs the final case template.
- **Does not decide the write policy, top-k, or threshold.** Those are Phase 2/3 decisions ([03](docs/memory-layer/03-write-path.md), [04](docs/memory-layer/04-read-path.md)).
- **Does not touch ground truth.** [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) §5 / [OQ-2](docs/memory-layer/07-open-questions.md#oq-2--does-ground-truth-feed-the-memory-store) is explicitly open; nothing here assumes an answer.
- **Does not add `data/` to `.gitignore`.** It should be ignored before any real run writes to it — but that's a `.gitignore` change and belongs in its own commit, not folded into memory-layer setup ([`CLAUDE.md`](CLAUDE.md)).

---

## 8. Quick troubleshooting

| Symptom | Likely cause |
|---|---|
| `collection.query` distances don't behave like cosine (e.g. unbounded, or 0 for dissimilar vectors) | Space defaulted to L2 — the `metadata={"hnsw:space": ...}` key was silently ignored, likely an API-version mismatch. Recheck step 2. |
| `embed()` returns different vectors for identical text | Model not in eval mode, or gradients not disabled, or two different model instances in use. Re-check step 5. |
| `PersistentClient` raises when reused across two processes at once | Chroma's SQLite backend doesn't support concurrent writers well — this is consistent with [01 §Ordering guarantee](docs/memory-layer/01-architecture.md#ordering-guarantee): the stream must be processed strictly sequentially, not in parallel. |
| Import of `torch` is slow or pulls a large CUDA wheel you didn't want | Force the CPU wheel explicitly: `pip install torch --index-url https://download.pytorch.org/whl/cpu`. |

---

## Next steps

Once this is verified working: measure the rendered-template token distribution to close [OQ-8](docs/memory-layer/07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2), get the Layer 2 output contract settled to close [OQ-9](docs/memory-layer/07-open-questions.md#oq-9--what-does-layer-2-emit), and only then start on `CaseRenderer` per [02 — Case Schema](docs/memory-layer/02-case-schema.md).
