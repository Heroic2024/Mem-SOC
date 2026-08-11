# Memory Layer — Vector DB Schema Design

> **Status: proposal, blocked.** Grounded in the actual alert payload (`memory/final_alert_fuzzers.json`), traced field-by-field back to the Layer 2 code that produces it.
>
> Design rationale lives in [`docs/memory-layer/02-case-schema.md`](../docs/memory-layer/02-case-schema.md). **That document was written against assumptions the real payload does not satisfy** — see [§2](#2-gap-against-the-existing-schema-doc). This file records what can actually be built, and what is blocked.
>
> Per [`CLAUDE.md`](../CLAUDE.md): no dataset field, metric, or schema entry below is invented. Anything not derivable from verified code is marked **BLOCKED** rather than guessed.

---

## 1. What the detector actually emits

Verified against the code, not just the sample file.

```json
{
    "attack": "Fuzzers",
    "confidence": 0.7228,
    "src_port": 48171,
    "dst_port": 445,
    "protocol": 6,
    "top_features": ["L4_SRC_PORT", "ICMP_TYPE", "SRC_TO_DST_IAT_MAX", "L4_DST_PORT", "LONGEST_FLOW_PKT"],
    "shap_explanation": [ {"feature": "...", "shap_value": 0.0, "impact": "positive|negative"} ]
}
```

| Field | Type | Produced by | Usable as |
|---|---|---|---|
| `attack` | str | `train_multiclass.py:62` — LightGBM `predict()` | `detector_label` |
| `confidence` | float | `train_multiclass.py:64` — `predict_proba().max()` | `detector_score` ✅ |
| `src_port` | int | `alert_generator.py:18` ← `L4_SRC_PORT` | metadata (low value — ephemeral) |
| `dst_port` | int | `alert_generator.py:19` ← `L4_DST_PORT` | metadata (**high value** — service identity) |
| `protocol` | int | `alert_generator.py:20` ← `PROTOCOL` | metadata (**high value**) |
| `top_features` | list[str] | `train_multiclass.py:68-83` | ⚠️ **see B2 — not per-alert** |
| `shap_explanation` | list[obj] | *not emitted by `AlertGenerator`* | ⚠️ **see B3 — not reproducible** |

**Good news:** `confidence` exists. This closes half of [OQ-9](../docs/memory-layer/07-open-questions.md#oq-9--what-does-layer-2-emit) — the detector *does* expose a per-alert score, so `detector_score` is available and the `confidence_gated` write policy remains implementable.

---

## 2. Gap against the existing schema doc

[`02-case-schema.md`](../docs/memory-layer/02-case-schema.md) proposes a 9-line embedding template. Against the real payload:

| Template line | Needs | Status |
|---|---|---|
| `ALERT {day} {timestamp}` | timestamp | ❌ dropped at `feature_engineering.py:23-24` |
| `{src_ip}:{src_port} -> {dst_ip}:{dst_port} {protocol}` | IPs | ❌ dropped at `feature_engineering.py:21-22` (ports/protocol survive) |
| `Detector: {label} score {score}` | label, score | ✅ **available** |
| `Volume:` / `Rate:` / `Size:` / `Timing:` / `Flags:` / `Shape:` | flow feature **values** | ❌ **not in the alert at all** |

**Six of nine lines cannot be rendered, and a seventh only partially.** The alert carries feature *names* (via `top_features` / `shap_explanation`) but never feature *values* — `LONGEST_FLOW_PKT` appears as a string, never as a number.

This is the exact failure mode [`02-case-schema.md`](../docs/memory-layer/02-case-schema.md#feature-selection) warned about and [R7](../docs/memory-layer/06-risks-and-limitations.md#r7--numeric-features-in-a-text-embedding-space) rates as structural — except worse than anticipated, because the numeric features are absent rather than merely unanchored.

> **`02-case-schema.md` is now stale.** Its template, its CICIDS2017 feature names, and its worked example all describe data this pipeline does not produce. It needs revision once the blockers below are resolved. I have not edited it — it is a team-owned design doc and out of scope for this task.

---

## 3. Blocking issues

Each is evidenced, none is resolved here. Numbered from B1 to avoid colliding with `OQ-1`–`OQ-9` in [`07-open-questions.md`](../docs/memory-layer/07-open-questions.md).

### B1 — Which dataset is authoritative? ✅ RESOLVED 2026-08-10

**Decision:** CICIDS2017 is **dropped as outdated**. The project uses the NetFlow v3 datasets:

| Dataset | Role |
|---|---|
| `NF-UNSW-NB15-v3` | What the detector is trained on **today** (`main.py:18`) |
| `NF-CICIDS2018-v3` | **Target** for model training |

Docs updated accordingly: `PROJECT_BRIEF.md`, `README.md`, `docs/memory-layer/{02,04,README}`, `my_guide.md`, `LogGeneration/README.md`.

**What this settles:** the feature schema. Both datasets share the NetFlow v3 column set (55 columns — 53 features + `Label` + `Attack`; 48 features survive into `X`), so the embedding template is portable across the switch.

**What this does NOT settle — see B8.** The two datasets have **disjoint attack label vocabularies**, and `detector_label` is embedded text.

### B2 — `top_features` is global, not per-alert 🔴 zero retrieval signal

`MulticlassTrainer.top_features()` (`train_multiclass.py:68-83`) returns:

```python
importance = pd.Series(self.model.feature_importances_, index=sample.columns)
return importance.sort_values(ascending=False).head(top_k).index.tolist()
```

`feature_importances_` is LightGBM's **global** importance over the whole trained model. `sample` is used only for `.columns`. **The returned list is therefore identical for every alert.**

Consequence for this layer: putting `top_features` in the embedding text adds a constant string to every document. It contributes **nothing** to similarity while consuming tokens. It should be metadata at most, or dropped.

Note `LocalExplainer.explain()` (`local_explainer.py:30-40`) *does* compute genuine per-sample SHAP rankings — but `main.py` never calls it for the alert.

### B3 — `shap_explanation` is not reproducible from the repo 🟠

`AlertGenerator.generate()` (`alert_generator.py:14-23`) has no `shap_explanation` parameter and does not emit one. The sample JSON contains a block the current code cannot produce, so it was generated by modified or unmerged code.

Before this field can be schema'd, it must be reproducible and its ordering guaranteed deterministic. (In the sample it is sorted by `|shap_value|` descending — that ordering must be *guaranteed*, not incidental, or the rendered text varies between runs and breaks embedding determinism.)

### B4 — No stable `alert_id` 🔴 blocks evaluation, not just retrieval

The alert has no identifier. [`02-case-schema.md`](../docs/memory-layer/02-case-schema.md#identity-and-provenance) requires one to join a stored case back to its alert, its ground-truth label, and its scoring record — and [`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §7 Phase 0 requires "complete data consistency between layers."

Without it, Phase 4 cannot score verdicts against ground truth. This blocks the *experiment*, not merely the schema.

### B5 — No `detector_version` 🟡

Nothing in the alert identifies the frozen model that produced it. [`CLAUDE.md`](../CLAUDE.md) makes detector weights a protected component; without a version string an accidental change is undetectable after the fact.

### B6 — Embedded detector label ≈ label-based retrieval 🟠 experimental-validity risk

With only `attack`, three integers, and feature names available, `Fuzzers` is by far the strongest lexical token in the document. Similarity would be driven mainly by **detector label + destination port**.

[`04-read-path.md`](../docs/memory-layer/04-read-path.md#metadata-filters) explicitly disqualifies `{"detector_label": ...}` as a `where` filter because it means "memory can no longer contradict the detector — which is one of the things it is supposed to be able to do." **Embedding the label so dominantly achieves the same effect implicitly, without the filter being visible in the config.**

This needs a decision, and it becomes much less severe if B7 is fixed (real feature values dilute the label's dominance).

### B7 — Flow feature *values* are discarded 🔴 highest-leverage fix

`main.py:82` passes `flow=sample.iloc[0]` — **the entire flow record** — into `AlertGenerator.generate()`, which then extracts three fields and drops the rest (`alert_generator.py:18-20`).

All ~45 remaining NetFlow features are in hand at the moment the alert is built and are thrown away. Restoring even 10–15 of them is the single highest-value change available to the memory layer, and it costs a few lines in Layer 2.

### B8 — The two NF datasets have disjoint label vocabularies 🔴 new, created by the B1 decision

B1 settles the *feature* schema — both datasets share the NetFlow v3 columns. It does **not** settle the *label* vocabulary, and the two do not overlap:

| Dataset | `Attack` values |
|---|---|
| NF-UNSW-NB15-v3 | `Benign`, `Fuzzers`, `Exploits`, `Generic`, `Reconnaissance`, `DoS`, `Analysis`, `Backdoor`, `Shellcode`, `Worms` |
| NF-CICIDS2018-v3 | `Benign`, `Bot`, `Brute_Force_-XSS`, … — *verified by sampling the tail of the CSV only; the full set has not been enumerated* |

`Fuzzers` does not exist in CICIDS2018. `Bot` does not exist in UNSW-NB15.

**Why this blocks the memory layer specifically:** `detector_label` is rendered into the embedding text ([§5](#5-embedding-text)), and under the thin v0.1 representation it is the single strongest lexical token. Retraining on a different dataset therefore:

1. changes the embedded text for every alert → **`schema_version` bump**;
2. makes every case stored under the old vocabulary **unretrievable-by-meaning and non-comparable** — `Fuzzers` precedent is noise to a `Bot` alert;
3. requires a **new store**, since [`CLAUDE.md`](../CLAUDE.md) forbids wiping or regenerating the existing one.

**The question for the team:** which dataset does the *memory-layer experiment* run on? The Arm A / Arm B comparison must run end-to-end on one of them. If it is NF-CICIDS2018-v3, then:

- `final_alert_fuzzers.json` is **unrepresentative** — the schema is currently being designed around a label that will not exist;
- the full CICIDS2018 `Attack` vocabulary must be enumerated before the schema locks;
- no store should be built against the UNSW-NB15-trained detector, because it will be discarded.

Building the memory layer now against UNSW-NB15 and switching later means re-rendering and re-running everything. **Deciding this before implementation starts costs nothing; deciding it after costs a full re-run of both arms.**

---

## 4. The three-way split

Unchanged in principle from [`02-case-schema.md §The three-way split`](../docs/memory-layer/02-case-schema.md#the-three-way-split) — only the field lists change.

| Part | Chroma field | Job |
|---|---|---|
| Embedding text | `documents` | Defines what *similar* means |
| Metadata | `metadatas` | Defines what can be filtered and cited |
| Sidecar (JSONL) | — | Full rationale, full feature vector, audit trail |

---

## 5. Embedding text

### 5a. What is renderable today (v0.1-draft — **not recommended**)

```
ALERT
Service: TCP port 445 microsoft-ds, source port 48171
Detector: Fuzzers score 0.72
Signals: L4_DST_PORT +2.36, MIN_TTL +0.58, NUM_PKTS_128_TO_256_BYTES +0.55, DNS_QUERY_TYPE +0.25, RETRANSMITTED_OUT_BYTES +0.16
```

Roughly 80–110 word-piece tokens (NetFlow feature names tokenize into many pieces). Comfortably inside MiniLM's 256-token limit — so [R5](../docs/memory-layer/06-risks-and-limitations.md#r5--silent-truncation-at-the-token-limit) is currently **low risk**.

But it encodes only four meaningful degrees of freedom: predicted label, destination port, protocol, and which features the model looked at. Two unrelated flows that the detector happens to label `Fuzzers` toward port 445 are near-identical under this representation. **This is thin enough that retrieval quality is questionable before a single line is written** — and it is why B6 and B7 matter.

### 5b. What it becomes if B7 is fixed (target)

```
ALERT
Service: TCP port 445 microsoft-ds, source port 48171
Detector: Fuzzers score 0.72
Volume: 12 in / 8 out pkts, 1840 / 640 bytes
Rate: in 14720 B/s, out 5120 B/s over 125 ms
Size: longest 1460, shortest 60, avg 154
TTL: min 62 max 64
Flags: TCP 27 client 22 server 18
Timing: src->dst IAT max 41 avg 12, dst->src IAT max 33 avg 9
Retransmit: 0 in / 0 out bytes
```

This restores the axes analysts actually reason about, dilutes the detector label's lexical dominance (mitigating B6), and gives cosine similarity something structural to work with.

⚠️ **Re-measure the token budget if this is adopted.** Adding 10–15 valued features could push p99 toward or past 256 tokens, which would trigger [R5](../docs/memory-layer/06-risks-and-limitations.md#r5--silent-truncation-at-the-token-limit) silent truncation and reopen [OQ-8](../docs/memory-layer/07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2) (model choice). Measure before locking, not after.

### Rendering rules

Carried over unchanged from [`02-case-schema.md §Rendering rules`](../docs/memory-layer/02-case-schema.md#rendering-rules) — fixed field order, every line always present, fixed decimal precision, `n/a` for null/NaN/Inf, resolved protocol and port names, no scaling, one shared `CaseRenderer` for both paths.

One addition specific to this payload: **SHAP entry order must be explicitly sorted** (by `|shap_value|` descending) in the renderer, not inherited from the producer. See B3.

---

## 6. Metadata

Chroma accepts only `str`, `int`, `float`, `bool` — no `None`, no lists, no nesting. Use sentinels, never omit keys.

| Key | Type | Source | Status |
|---|---|---|---|
| `case_id` | str | `{run_id}:{seq:06d}` | ✅ generated by this layer |
| `run_id` | str | run config | ✅ |
| `seq` | int | stream position | ✅ |
| `schema_version` | str | `"0.1"` | ✅ |
| `created_at` | str | write time, ISO-8601 | ✅ |
| `src_port` | int | alert | ✅ |
| `dst_port` | int | alert | ✅ |
| `protocol` | int | alert | ✅ |
| `protocol_name` | str | resolved `6`→`TCP` | ✅ derived |
| `dst_port_name` | str | resolved `445`→`microsoft-ds` | ✅ derived |
| `detector_label` | str | `attack` | ✅ |
| `detector_score` | float | `confidence` | ✅ |
| `verdict` | str | LLM (Layer 4) | ✅ closed vocab, pending Layer 4 |
| `confidence` | float | LLM | ✅ pending Layer 4 |
| `rationale_summary` | str ≤500 | LLM | ✅ pending Layer 4 |
| `precedent_used` | str | comma-joined case IDs | ✅ **required for error-propagation tracing** |
| `precedent_count` | int | — | ✅ |
| `alert_id` | str | — | 🔴 **BLOCKED — B4** |
| `detector_version` | str | — | 🟡 **BLOCKED — B5** |
| `src_ip` / `dst_ip` | str | — | 🔴 **BLOCKED** — dropped at `feature_engineering.py:21-22` |
| `timestamp` | str | — | 🔴 **BLOCKED** — dropped at `feature_engineering.py:23-24` |
| `attack_category` | str | — | 🟠 **BLOCKED — [OQ-3](../docs/memory-layer/07-open-questions.md#oq-3--where-does-attack_category-come-from)** + vocabulary depends on B1 |

**Deliberately absent: `ground_truth`.** Per [`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §5 and [OQ-2](../docs/memory-layer/07-open-questions.md#oq-2--does-ground-truth-feed-the-memory-store), labels are the evaluation oracle and live in the scoring log, joined by `alert_id` after the run. [`CLAUDE.md`](../CLAUDE.md) reserves this question — it is not decided here in either direction.

**`top_features` is deliberately excluded** from both embedding text and metadata while B2 stands: a constant value has no filtering or retrieval utility.

---

## 7. Sidecar record

`data/memory/<run_id>/cases.jsonl`, keyed by `case_id`. Holds the full untruncated rationale, both report views, **the complete flow feature vector as ingested**, the full `shap_explanation` array, all retrieval candidates with distances, and raw LLM token/latency metadata.

The complete SHAP array belongs here regardless of how B3 resolves — it is a list of dicts, which Chroma metadata cannot store, and it is never filtered on.

---

## 8. What Layer 2 must change

Ordered by value to this layer. **All of these are Layer 2 edits and out of scope for me** — flagged per [`CLAUDE.md`](../CLAUDE.md), not made.

| # | Change | Unblocks |
|---|---|---|
| 1 | Emit a stable `alert_id` per alert | B4 — and Phase 4 scoring |
| 2 | Pass through 10–15 flow feature **values**, not just names | B7, B6, R7 |
| 3 | Re-join `IPV4_SRC_ADDR`, `IPV4_DST_ADDR`, `FLOW_START_MILLISECONDS` | identity + timestamp metadata |
| 4 | Replace global `top_features` with `LocalExplainer`'s per-sample SHAP | B2 |
| 5 | Emit `detector_version` | B5 |
| 6 | Make `shap_explanation` reproducible with guaranteed ordering | B3 |

On (3): these columns are dropped from `X` at `feature_engineering.py:18-26`, but `X` is built via `self.df.drop(columns=...)`, which **preserves the index** — so they are recoverable by an index join against `df` without retraining or altering the frozen model. This does not touch detector weights or thresholds.

---

## 9. Schema versioning

`schema_version` starts at `"0.1"` and is **provisional**. Any change to the template, field set, rounding, or label wording is a version bump, and a store may contain only one version ([`02-case-schema.md §Schema versioning`](../docs/memory-layer/02-case-schema.md#schema-versioning)).

Because B1–B7 will all change the template, **expect the schema to be re-versioned before Phase 2.** Do not treat `0.1` as lockable — building a large store against it now guarantees rework.
