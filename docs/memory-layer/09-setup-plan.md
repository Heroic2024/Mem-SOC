# Memory Layer — Setup Plan, Requirements & Step Split

> Companion to [`SCHEMA_DESIGN.md`](./SCHEMA_DESIGN.md) (what the DB stores) and [`CHROMADB_SETUP_GUIDE.md`](../CHROMADB_SETUP_GUIDE.md) (the command-by-command install walkthrough).
>
> This file answers three things: **what we need**, **what you do**, **what I do** — and in what order.

---

## 1. Do we need an embedding model?

**Yes — it is not optional.** A vector database stores vectors; something has to produce them. Chroma can call an embedding function itself, but this project deliberately computes embeddings *outside* Chroma and passes them in explicitly, so that the one-model invariant is visible in code rather than buried in collection config ([`03-write-path.md`](../docs/memory-layer/03-write-path.md#what-is-written)).

It is also the single most safety-critical component in this layer: **[Invariant #1](../docs/memory-layer/README.md#invariants) — the same model instance embeds on both the write path and the read path.** A mismatch does not raise an error; retrieval keeps returning plausible-looking results that are meaningless ([R4](../docs/memory-layer/06-risks-and-limitations.md#r4--embedding-model-mismatch)).

### Candidate

`sentence-transformers/all-MiniLM-L6-v2`, named in [`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §6 — as an example ("e.g."), **not a commitment**. [OQ-8](../docs/memory-layer/07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2) requires the choice be justified by a token-budget measurement before it is locked, because [`CLAUDE.md`](../CLAUDE.md) makes it a protected component that can never be swapped afterwards.

### Requirements

| Requirement | Value | Notes |
|---|---|---|
| Package | `sentence-transformers` (pulls `torch`, `transformers`, `tokenizers`) | CPU build is sufficient |
| Model download | ~90 MB, once | From HuggingFace on first `SentenceTransformer(...)` call |
| Network | **Once**, for the download | Cached to `%USERPROFILE%\.cache\huggingface\hub`; fully offline afterwards |
| Disk (install) | ~1.5–2.5 GB | `torch` CPU wheel alone is ~200–250 MB |
| RAM (runtime) | ~0.7–1 GB process | Model resident ~100–200 MB + torch overhead |
| GPU | **Not needed** | Pin `device="cpu"` explicitly and record it — CPU and GPU give slightly different floats, which moves borderline cases across the similarity threshold |
| Output | 384 dimensions | Must match `dimensions` in config; validated at startup |
| Max input | **256 word-piece tokens** | Exceeding it truncates **silently** — [R5](../docs/memory-layer/06-risks-and-limitations.md#r5--silent-truncation-at-the-token-limit) |
| Normalization | `normalize_embeddings=True` | Explicit, so cosine behaves |
| Determinism | eval mode, gradients off, one shared instance | Verified at startup: same text twice → exact equality |

**Speed is a non-issue here.** Our rendered cases are ~100 tokens; CPU embedding is single-digit milliseconds each. Even a 10k-alert sequential run spends only a few minutes total on embedding.

**Token budget — measured 2026-08-15.** Rendering the full 44-feature template over a 2,598-row sample of the real dataset gives **p99 ≈ 184 estimated tokens** against MiniLM's 256 — ~28% headroom, and the distribution is tight (max 188) because the template is fixed-shape. [OQ-8](../docs/memory-layer/07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2)'s blocking measurement passes. Two caveats: it is a heuristic count, not a tokenizer run (no `transformers` installed yet — confirm at Step 5); and it holds **only if the alert is fixed-shape**, which is [B11](./SCHEMA_DESIGN.md#b11--shap-selected-features-make-the-alert-variable-shape--breaks-comparability). A variable-shape alert invalidates the measurement.

---

## 2. Vector DB requirements

| Requirement | Value | Notes |
|---|---|---|
| Package | `chromadb` | Apache 2.0; settled choice ([`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §6) |
| Mode | **`PersistentClient`, on-disk, always** | Never `EphemeralClient` — in-memory would make "memory persists across shifts" literally false |
| Server | None | Embedded library, no daemon, no container |
| Distance space | **cosine, set explicitly** | Default is L2; a threshold tuned for one is meaningless under the other, and nothing errors |
| Collection | one — `soc_cases` | Not partitioned by attack type or day; partitioning builds a label-shaped prior into the store |
| Disk | ~50–100 MB per 10k cases | 384 floats ≈ 1.5 KB/vector + HNSW index + SQLite metadata. Negligible. |
| RAM | Low tens of MB at our scale | Chroma is memory-resident ([R8](../docs/memory-layer/06-risks-and-limitations.md#r8--chromadb-scaling-characteristics)); irrelevant below ~10⁵ vectors |
| HNSW params | **defaults** | Tuning them makes retrieval quality a second variable |
| Store path | `data/memory/<run_id>/` | Run-scoped. Never shared, never cleared — a fresh store is a *new directory* |

### Two environment risks worth knowing before you install

**A. Python 3.13.** This machine has Python 3.13.2. `chromadb`'s support for 3.13 depends on version and on prebuilt wheels for its native dependencies. Verify the install actually succeeds before planning around it; if it fights you, a 3.11/3.12 virtualenv is the low-drama fallback.

**B. Do not install into the detector's environment.** `requirements/research-lock.txt` pins `numpy==2.4.6`, `scikit-learn==1.9.0`, `lightgbm==4.7.0`. Installing `torch` alongside them can cause pip to re-resolve `numpy`/`scipy`, which can shift LightGBM's numerics. Detector weights and thresholds are a **protected component** ([`CLAUDE.md`](../CLAUDE.md)) — a dependency bump is a silent way to violate that freeze.

> **Use a separate virtualenv for the memory layer.** This is the recommendation; it costs nothing and removes the risk entirely.

---

## 3. Steps for YOU

Ordered. Steps 1–2 block essentially all of my implementation work.

### ✅ Step 1 — Resolve the dataset conflict (B1) — DONE 2026-08-10

CICIDS2017 dropped as outdated. NF-UNSW-NB15-v3 is what the detector is trained on today; NF-CICIDS2018-v3 is the target for model training. Docs updated across the repo.

### 🔴 Step 1b — Which dataset does the *experiment* run on? (B8)

B1 settled the feature schema but not the label vocabulary — the two NF datasets have **disjoint** `Attack` values (`Fuzzers` vs `Bot`), and `detector_label` is embedded text.

Pick the dataset the Arm A / Arm B comparison runs on end-to-end. If it is NF-CICIDS2018-v3, the current `Fuzzers` sample is unrepresentative, the full CICIDS2018 label set must be enumerated, and **no store should be built against the UNSW-NB15 detector** — it would be discarded on retrain. See [`SCHEMA_DESIGN.md §B8`](./SCHEMA_DESIGN.md#b8--the-two-nf-datasets-have-disjoint-label-vocabularies--new-created-by-the-b1-decision).

### 🔴 Step 2 — Decide the reserved & schema-blocking questions

| Question | Why it blocks |
|---|---|
| [OQ-2](../docs/memory-layer/07-open-questions.md#oq-2--does-ground-truth-feed-the-memory-store) — does ground truth enter memory? | **Explicitly reserved.** [`CLAUDE.md`](../CLAUDE.md) forbids me implementing either interpretation without your confirmation. |
| [OQ-1](../docs/memory-layer/07-open-questions.md#oq-1--does-the-embedded-text-include-the-verdict) — is the verdict in the embedding text? | Determines whether read and write text are symmetric. Recommendation: alert-only. |
| [OQ-3](../docs/memory-layer/07-open-questions.md#oq-3--where-does-attack_category-come-from) — source of `attack_category`? | Recommendation: the LLM's own categorization. |
| [OQ-5](../docs/memory-layer/07-open-questions.md#oq-5--what-is-the-phase-2-default-write-policy) — default write policy? | Recommendation: `write_all`, so error propagation stays observable. |
| **B6** — should the detector label be in the embedding text? | Risks turning retrieval into label lookup. See [`SCHEMA_DESIGN.md §B6`](./SCHEMA_DESIGN.md#b6--embedded-detector-label--label-based-retrieval--experimental-validity-risk). |
| **B11** — will the alert carry a fixed 44-feature Core block? | 🔴 **The one that blocks everything.** A SHAP-selected, per-alert feature subset cannot be embedded: the shape varies, and the subset is chosen *by the predicted class*, so similarity would silently become label lookup. Recommendation: fixed Core block for the embedding, SHAP top-10 for the LLM prompt. See [`SCHEMA_DESIGN.md §B11`](./SCHEMA_DESIGN.md#b11--shap-selected-features-make-the-alert-variable-shape--breaks-comparability). |
| **D1** — magnitude tokens in the embedding text? | MiniLM does not encode numeric magnitude. Recommendation: fixed order-of-magnitude buckets on volume/rate/duration only. Changes every case's text, so it must be settled pre-store. See [`SCHEMA_DESIGN.md §5d`](./SCHEMA_DESIGN.md#5d-open-decision--magnitude-tokens-d1). |
| ~~**B9**~~ ✅ closed | IPs never enter the alert (confirmed `alert_generator.py:19-21`). Standing constraint: never re-join them — source IP predicts the label with **100% accuracy** on this dataset. |
| ~~Tier 1 vs Tier 2~~ ✅ measured | Tier 2 (44 features) estimates **p99 ≈ 184 tokens** vs MiniLM's 256 — comfortable. Recommendation: Tier 2. Confirm with the real tokenizer at Step 5. |

### 🟠 Step 3 — Approve the Layer 2 alert changes

The six changes in [`SCHEMA_DESIGN.md §8`](./SCHEMA_DESIGN.md#8-what-layer-2-must-change). They are Layer 2 edits, outside this layer's scope — I will not touch `src/memsoc/detection/` without your explicit go-ahead. The two that matter most:

- a stable **`alert_id`** (without it, Phase 4 cannot score at all)
- **flow feature values** in the alert, not just feature names

### 🟡 Step 4 — Give me a real alert *stream*

`final_alert_fuzzers.json` is one alert, from `X_test_multi.iloc[[0]]`. To measure the token distribution, exercise retrieval, and test near-duplicate saturation ([R6](../docs/memory-layer/06-risks-and-limitations.md#r6--near-duplicate-saturation)), I need a representative multi-alert sample — a few hundred alerts spanning several attack classes is plenty.

### 🟡 Step 5 — Create the environment

```bash
python -m venv .venv-memory
.venv-memory\Scripts\activate
pip install chromadb sentence-transformers torch
pip freeze | findstr /I "chromadb sentence-transformers torch"
```

Then follow [`CHROMADB_SETUP_GUIDE.md`](../CHROMADB_SETUP_GUIDE.md) steps 2–6 to verify the install (cosine space, determinism, round-trip). Record the resolved versions — they are experimental-control state, not just hygiene.

### 🟡 Step 6 — Add `data/` to `.gitignore`, as its own commit

The store directory must never be committed ([`CLAUDE.md`](../CLAUDE.md)). `.gitignore` currently does not cover `data/`. [`CLAUDE.md`](../CLAUDE.md) also forbids me changing `.gitignore` as a side effect of a feature task — so this is a deliberate, standalone change. Say the word and I'll do it as a single-purpose commit.

---

## 4. Steps for ME

Each is blocked until the step in the right-hand column clears. I will not start any of them on assumption.

| # | What I build | Blocked by |
|---|---|---|
| 1 | Revise `SCHEMA_DESIGN.md` to a lockable v1.0; propose revisions to `02-case-schema.md` | Your steps 1–3 |
| 2 | Token-budget measurement over the real stream → closes [OQ-8](../docs/memory-layer/07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2), justifies the model lock | Step 4 + schema v1.0 |
| 3 | `CaseRenderer` — the single shared renderer, with the hard token-limit assertion | schema v1.0 |
| 4 | `MemoryStore` — persistent client, cosine space + behavioural verification, run-scoped paths, abort-on-collision | Step 5 |
| 5 | `EmbeddingFunction` — one shared instance, eval mode, determinism + reference-corpus hash checks | Step 5, [OQ-8](../docs/memory-layer/07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2) |
| 6 | `MemoryLayer` protocol + `NullMemoryLayer` / `ChromaMemoryLayer`, and the test that Arm A opens no store and loads no model | 3–5 |
| 7 | `Writer` + write policy; `Retriever` + threshold/top-k; retrieval & write logs | 6, [OQ-5](../docs/memory-layer/07-open-questions.md#oq-5--what-is-the-phase-2-default-write-policy) |
| 8 | `inspect` / `verify` / `snapshot` / `export` operations | 4 |

Note the ordering constraint from [`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §7: **Phase 1 (Arm A baseline) is built before Phase 2 (Arm B)** — "so there is something to beat." Items 6–7 above are Phase 2 work and should not land before the baseline exists.

---

## 5. Where we are

**Phase 0 — Setup & data prep. In progress, partially blocked.**

| Phase 0 task ([`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §7) | Status |
|---|---|
| Find the ML detector | ✅ Done — LightGBM multiclass, `src/memsoc/detection/` |
| Define the detector output format | 🟠 **Partial** — an alert exists and exposes `confidence`, but lacks `alert_id`, feature values, and `detector_version` |
| Install ChromaDB + embedding model | ⬜ Not started — requirements and walkthrough ready, nothing installed |
| Persistent mode from the start | ✅ Decided and documented; unimplemented |
| Preprocess the dataset | 🟠 Exists in `src/memsoc/detection/` against NF-UNSW-NB15-v3; not yet run against the NF-CICIDS2018-v3 target (B8) |
| Data consistency between layers | 🔴 **Blocked** — no stable `alert_id` (B4) |
| **Define the case schema** | 🟠 **Field universe fixed (48 features, verified 2026-08-15); allocation drafted, not lockable** — see [`SCHEMA_DESIGN.md §2b`](./SCHEMA_DESIGN.md#2b-the-feature-universe--verified) |

**Nothing in the memory layer is implemented.** No package installed, no store created, no code written. That is the correct state: the schema determines the embedding text, the embedding text determines the token budget, and the token budget determines the model lock — which is irreversible. Building against v0.1 now would guarantee a re-render of every stored case.

**The critical path is Step 1b (which dataset the experiment runs on) → Step 3 (alert payload) → schema v1.0 → model lock → implementation.**
