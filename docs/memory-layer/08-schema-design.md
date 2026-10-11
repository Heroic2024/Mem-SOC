# Memory Layer — Vector DB Schema Design

> **Status: proposal, blocked.** Grounded in the actual alert payload (`memory/final_alert_fuzzers.json`), traced field-by-field back to the Layer 2 code that produces it.
>
> Design rationale lives in [`docs/memory-layer/02-case-schema.md`](../docs/memory-layer/02-case-schema.md). **That document was written against assumptions the real payload does not satisfy** — see [§2](#2-gap-against-the-existing-schema-doc). This file records what can actually be built, and what is blocked.
>
> Per [`CLAUDE.md`](../CLAUDE.md): no dataset field, metric, or schema entry below is invented. Anything not derivable from verified code is marked **BLOCKED** rather than guessed.
>
> **Updated 2026-08-15** — [§2b](#2b-the-feature-universe--verified) pins the exact 48-column feature universe, verified against `NF-UNSW-NB15-v3.csv` and `NetFlow_v3_Features.csv`; [§5](#5-embedding-text) and [§6](#6-metadata) are rewritten field-by-field against it.
>
> Closed this round: [B3](#b3--shap_explanation-is-not-reproducible-from-the-repo--resolved-2026-08-15) (per-alert SHAP now exists and is deterministically ordered), [B9](#b9--host-identity-is-a-perfect-ground-truth-oracle--closed-2026-08-15--standing-constraint) (IPs never enter the alert — now a standing constraint), [B10](#b10--token-budget--estimated-comfortable-confirm-with-the-real-tokenizer) (token budget measured, comfortable).
>
> **Open and blocking: [B11](#b11--shap-selected-features-make-the-alert-variable-shape--breaks-comparability)** — a SHAP-selected, variable-shape alert cannot serve as the embedding document. See [§5e](#5e-three-text-surfaces-three-budgets--do-not-conflate-them) for the surface each text serves.

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

## 2b. The feature universe — verified

Everything below is read directly from `data/NF-UNSW-NB15-v3/.../NF-UNSW-NB15-v3.csv` and cross-checked against `NetFlow_v3_Features.csv`. **The two agree exactly** — no column in the CSV is missing from the feature dictionary, and no documented feature is absent from the CSV. (`NetFlow_v3_Features.csv` has trailing whitespace in the eight IAT feature names; strip on read.)

### The arithmetic

| | Count | |
|---|---|---|
| CSV columns | **55** | |
| Labels | 2 | `Label` (binary 0/1), `Attack` (10-class string) |
| Dropped at `feature_engineering.py:18-26` | 5 | `IPV4_SRC_ADDR`, `IPV4_DST_ADDR`, `FLOW_START_MILLISECONDS`, `FLOW_END_MILLISECONDS`, `DNS_QUERY_ID` |
| **Features seen by the model (`X`)** | **48** | the classification feature universe |

This confirms the count asserted in [B1](#b1--which-dataset-is-authoritative--resolved-2026-08-10). **The 48 are the authoritative field universe for the case schema** — the memory layer may only describe a case in terms the detector actually saw, plus fields the alert carries about itself.

**Dataset shape:** 2,365,424 rows. `Attack` distribution (stride sample of 63,933 rows, every 37th row): `Benign` 94.6%, `Exploits` 1.83%, `Fuzzers` 1.40%, `Generic` 0.85%, `Reconnaissance` 0.72%, `DoS` 0.24%, `Backdoor` 0.19%, `Shellcode` 0.10%, `Analysis` 0.06%, `Worms` 0.008% (5 rows in sample). `Worms` and `Analysis` are rare enough that a small replayed stream may contain none — relevant to stream design, not to the schema.

### The 48, grouped, with distribution evidence

`nuniq` / `zero%` are from the same stride sample. They drive the embed/metadata/drop decisions in [§5](#5-embedding-text) and [§6](#6-metadata) — a feature that is constant carries no similarity signal regardless of how important it is to the classifier.

| # | Family | Features | Notes |
|---|---|---|---|
| 1–4 | **Identity / service** | `L4_SRC_PORT`, `L4_DST_PORT`, `PROTOCOL`, `L7_PROTO` | `PROTOCOL` nuniq 41, `L7_PROTO` nuniq 62. Highest-value metadata in the set. |
| 5–8 | **Volume** | `IN_BYTES`, `IN_PKTS`, `OUT_BYTES`, `OUT_PKTS` | Full range; `OUT_*` zero 2.9% (one-way flows). |
| 9–11 | **TCP flags** | `TCP_FLAGS`, `CLIENT_TCP_FLAGS`, `SERVER_TCP_FLAGS` | nuniq 11–12, zero ~24% (non-TCP). Low cardinality → good metadata, weak text. |
| 12–14 | **Duration** | `FLOW_DURATION_MILLISECONDS`, `DURATION_IN`, `DURATION_OUT` | zero 5–21%. |
| 15–16 | **TTL** | `MIN_TTL`, `MAX_TTL` | nuniq 10/13 — near-categorical. Median 31/32; attack traffic sits at 254/255 (see [B9](#b9--host-identity-is-a-perfect-ground-truth-oracle--do-not-embed-do-not-filter-on-it)). |
| 17–20 | **Packet size** | `LONGEST_FLOW_PKT`, `SHORTEST_FLOW_PKT`, `MIN_IP_PKT_LEN`, `MAX_IP_PKT_LEN` | `MAX_IP_PKT_LEN` is identical to `LONGEST_FLOW_PKT` in every sampled row (both nuniq 780, same min/median/max) — **redundant, embed one**. |
| 21–22 | **Bytes/sec** | `SRC_TO_DST_SECOND_BYTES`, `DST_TO_SRC_SECOND_BYTES` | ⚠️ **contain `inf`** (zero-duration flows). Float, unbounded. **Excluded from embedding text** — see rendering rules. |
| 23–26 | **Retransmission** | `RETRANSMITTED_{IN,OUT}_{BYTES,PKTS}` | zero 26–29%. |
| 27–28 | **Throughput** | `SRC_TO_DST_AVG_THROUGHPUT`, `DST_TO_SRC_AVG_THROUGHPUT` | int, finite — the safe stand-in for 21–22. |
| 29–33 | **Packet-size histogram** | `NUM_PKTS_UP_TO_128_BYTES`, `..._128_TO_256_...`, `..._256_TO_512_...`, `..._512_TO_1024_...`, `..._1024_TO_1514_BYTES` | zero 59–80% for the upper four. Shape signature — cheap and discriminative as one line. |
| 34–35 | **TCP window** | `TCP_WIN_MAX_IN`, `TCP_WIN_MAX_OUT` | zero ~25%. |
| 36–37 | **ICMP** | `ICMP_TYPE`, `ICMP_IPV4_TYPE` | zero 26%. `ICMP_TYPE` = type×256+code per the dictionary. |
| 38–40 | **Application** | `DNS_QUERY_TYPE`, `DNS_TTL_ANSWER`, `FTP_COMMAND_RET_CODE` | zero 81–85%, nuniq 8–12. Sparse; meaningful only for the matching protocol. |
| 41–48 | **Inter-arrival time** | `{SRC_TO_DST,DST_TO_SRC}_IAT_{MIN,MAX,AVG,STDDEV}` | ⚠️ `SRC_TO_DST_IAT_MIN` is zero in **99.9%** of sampled rows (nuniq 6); `DST_TO_SRC_IAT_MIN` is zero in **100.0%** (nuniq 8, none in sample). **Both are degenerate — exclude from embedding text.** `MAX`/`AVG`/`STDDEV` are informative. |

### The five dropped columns

Not features, but three of them matter to this layer:

| Column | Why dropped from `X` | Value to memory layer |
|---|---|---|
| `IPV4_SRC_ADDR`, `IPV4_DST_ADDR` | Identifiers, not behaviour | Audit/citation only — **never embedded, never filtered on**. See [B9](#b9--host-identity-is-a-perfect-ground-truth-oracle--do-not-embed-do-not-filter-on-it). |
| `FLOW_START_MILLISECONDS` | Absolute time, not behaviour | Stream ordering + `alert_id` derivation + human-readable reports. Range: 2015-01-22 11:50:14 → 2015-02-18 12:29:24 UTC. **Not monotonic in file order** — the CSV is not sorted by time, so stream order must be defined explicitly, not assumed. |
| `FLOW_END_MILLISECONDS` | Same | Redundant with start + `FLOW_DURATION_MILLISECONDS`. |
| `DNS_QUERY_ID` | Random per-query transaction ID | None. Correctly dropped everywhere. |

Per [§8](#8-what-layer-2-must-change) note (3), the first three are recoverable by index join without touching the frozen model.

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

### B3 — `shap_explanation` is not reproducible from the repo ✅ RESOLVED 2026-08-15

**Was:** `AlertGenerator.generate()` had no `shap_explanation` parameter, so the sample JSON contained a block the code could not produce.

**Now resolved in the repo** — re-verified against current code:

- `alert_generator.py:12,27-29` accepts and emits `shap_explanation`.
- `main.py:349-354` calls `SHAPExplainer.explain(sample, top_k=10)` per alert, and `main.py:398-404` passes the result through.
- `shap_explainer.py:36-44` selects the SHAP column for the **predicted class**, and `:136-141` sorts by `abs(shap_value)` descending. Python's sort is stable, so ties fall back to column order — **the ordering is deterministic**, which is what this blocker required.

Residual caveats, neither blocking:

1. `LocalExplainer` (`local_explainer.py`) is now a redundant second implementation that returns bare names and calls `shap.plots.waterfall` (blocking GUI). `SHAPExplainer` is the one in use. Not my file; noted only so the schema is unambiguous about its source.
2. The alert now carries **two** feature-importance blocks — `top_features` (global, see [B2](#b2--top_features-is-global-not-per-alert--zero-retrieval-signal)) and `shap_explanation` (per-alert). Only the second is real signal. The schema uses `shap_explanation` and ignores `top_features`.

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

### B9 — Host identity is a perfect ground-truth oracle ✅ CLOSED 2026-08-15 — standing constraint

**Confirmed closed by design decision (2026-08-15): the alert never carries IP addresses.** `AlertGenerator.generate()` (`alert_generator.py:19-21`) takes only `L4_SRC_PORT`, `L4_DST_PORT`, `PROTOCOL` from the flow, so no IP can reach the memory layer. **Layer 2 change (3) in [§8](#8-what-layer-2-must-change) is therefore withdrawn for the IP columns** — do not re-join them.

The finding is recorded because it is the *reason* the constraint exists, and because "add the IPs, they'd help retrieval" is an obvious-looking future suggestion that must be refused. Over a stride sample of 139,144 rows:

- The capture contains only **39 distinct source IPs and 39 distinct destination IPs** — it is a small synthetic testbed, not internet traffic.
- **100.0% of source IPs are label-pure.** Every IP is either 100% benign or 100% attack.
- All attack traffic originates from exactly four addresses: `175.45.176.0`–`175.45.176.3`. Every other host is benign in every sampled flow.

`IPV4_SRC_ADDR` alone therefore predicts `Label` with perfect accuracy on this dataset. Consequences:

1. **The IP must never enter the embedding text.** Cosine similarity over a document containing `175.45.176.0` would retrieve precedent by attacker identity — near-perfect retrieval that says nothing about whether *memory* works. Arm B would win for a reason that has nothing to do with the research question.
2. **It must never be a `where` filter**, for the same reason [`04-read-path.md`](../docs/memory-layer/04-read-path.md#metadata-filters) disqualifies `detector_label`.
3. Not carrying it at all — the decision taken — is strictly safer than carrying it and relying on a retriever allowlist to hold. The cost is that a report cannot say "same host as case X"; that is an acceptable trade on a 39-host synthetic capture where host identity is not a meaningful analyst signal anyway.

Same caution, lower severity, applies to `FLOW_START_MILLISECONDS`: attacks in UNSW-NB15 occur in bounded capture windows, so a time-range filter is a partial oracle. It is also not currently in the alert. If it is added for ordering/audit (see [§8](#8-what-layer-2-must-change)), store it but never filter on it.

⚠️ **`MIN_TTL`/`MAX_TTL` are a partial version of the same problem** and cannot be excluded, because they *are* model features: benign flows sit at 31/32, the attacker subnet at 254/255. This is a property of the dataset ([`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §8, "dataset realism"), not something the schema can fix. Worth stating in the limitations write-up: on this dataset some retrieval signal is testbed artefact rather than genuine behavioural similarity.

### B10 — Token budget 🟡 estimated comfortable; confirm with the real tokenizer

Measured 2026-08-15 by rendering both templates over a 2,598-row stride sample of the actual dataset.

| Template | est. tokens p50 | p95 | **p99** | max | chars p99 |
|---|---|---|---|---|---|
| [Tier 1](#5b-tier-1--core-24-feature-template) (8 lines) | 112 | 115 | **116** | 120 | 384 |
| [Tier 2](#5c-tier-2--full-44-feature-template) (13 lines) | 176 | 182 | **184** | 188 | 606 |

**Tier 2 fits MiniLM's 256-token window with ~28% headroom.** My earlier 220–300 estimate was pessimistic; it assumed raw NetFlow column names in the text (`SRC_TO_DST_IAT_MAX`, which WordPiece shreds). The templates use short human labels instead (`fwd iat max`), which is both cheaper and better English for a sentence embedder. **Recommendation: Tier 2.**

Two caveats before this is called closed:

1. **This is a heuristic estimate, not a tokenizer run.** `sentence-transformers`/`transformers` are not installed on this machine (`tokenizers` 0.21.1 is, but MiniLM's vocab needs a download). The count models WordPiece behaviour on digits and punctuation; expect ±15%. Even at +25% Tier 2 lands ~230, still inside the window — the conclusion is robust, the number is not exact. Re-run with the real tokenizer as part of [`SETUP_PLAN.md`](./SETUP_PLAN.md) Step 5.
2. **The distribution is tight** (p50→max spans 12 tokens) because the template is fixed-shape. That property is worth protecting — see [B11](#b11--shap-selected-features-make-the-alert-variable-shape--breaks-comparability). A variable-shape document would have a long tail and this measurement would not transfer.

If the real tokenizer puts p99 above ~230, fall back to Tier 1 rather than changing the embedding model.

### B11 — SHAP-selected features make the alert variable-shape 🔴 breaks comparability

**Stated 2026-08-15: the alert will carry only the features with high confidence / high SHAP values, not the full flow record.** This is a reasonable instinct for the LLM prompt. For the embedding document it does not work, for three separate reasons.

**1. Similarity across different field sets is not a defined comparison.**
Alert A is described by `{IN_BYTES, MIN_TTL, TCP_FLAGS, …}`; alert B by `{L4_DST_PORT, DURATION_IN, ICMP_TYPE, …}`. Cosine similarity does not know a field is *missing* — it only sees text that isn't there. Absence and low-value become indistinguishable, and two flows that behaved identically can land far apart simply because SHAP ranked their features differently. The tight token distribution in [B10](#b10--token-budget--estimated-comfortable-confirm-with-the-real-tokenizer) is a symptom of the fixed shape; lose the shape and you lose that too.

**2. The SHAP subset is conditioned on the predicted class — so it encodes the label.**
`shap_explainer.py:36-44` picks the SHAP column **for the predicted class** before ranking. The selected feature set is therefore a fingerprint of what the detector decided. Retrieving on it means retrieving on the detector's label with extra steps — [B6](#b6--embedded-detector-label--label-based-retrieval--experimental-validity-risk) again, but structural instead of lexical, and invisible in the config. [`04-read-path.md`](../docs/memory-layer/04-read-path.md#metadata-filters) rules out filtering on `detector_label` precisely because memory must be able to *contradict* the detector. A document whose very shape is chosen by the detector cannot do that.

**3. The LLM cannot overturn a false positive using only the model's own top features.**
Objective 1 in [`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §2 is false-positive reduction. Overturning a false positive requires evidence the detector *under*-weighted — which is exactly what a top-SHAP filter removes. Feed the LLM only the features the model already found decisive and it becomes an explainer of the model's reasoning rather than an independent second opinion. Its verdict would correlate with the detector by construction, in **both** arms.

**Resolution — one payload, two consumers.** These are different jobs and neither needs to lose:

| Block | Contents | Consumed by |
|---|---|---|
| **Core** | fixed feature list, always the same fields in the same order ([Tier 2](#5c-tier-2--full-44-feature-template), 44 features, ~184 tokens) | embedding document (write + read), metadata, sidecar |
| **Signals** | per-alert `shap_explanation`, top-10, already sorted | **LLM prompt only** + sidecar. **Not embedded.** |

The LLM sees both — the full behavioural picture *and* what the model keyed on, which is strictly more useful for triage than either alone. The embedding sees only the Core block, so "similar" keeps meaning "behaved similarly" rather than "the model looked at the same things."

Cost of the fix: the alert JSON carries ~44 numbers, roughly 600 characters, instead of ~10. That is negligible against an LLM prompt measured in thousands of tokens.

**If the fixed-core block is rejected**, the memory layer has no stable basis for similarity, and [B10](#b10--token-budget--estimated-comfortable-confirm-with-the-real-tokenizer), [OQ-8](../docs/memory-layer/07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2) and the whole of [§5](#5-embedding-text) need rethinking from scratch. Flagging rather than assuming — this is a decision, not a defect.

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

### What B7 makes renderable — the allocation of all 48

Both tiers below assume [B7](#b7--flow-feature-values-are-discarded--highest-leverage-fix) is fixed, i.e. the alert carries feature *values*. Every one of the 48 is accounted for:

| Disposition | Count | Features |
|---|---|---|
| **Embedded (Tier 2)** | **44** | everything not listed below |
| **Metadata + sidecar only** | 4 | `SRC_TO_DST_SECOND_BYTES`, `DST_TO_SRC_SECOND_BYTES` — `inf`-valued and redundant with `*_AVG_THROUGHPUT`; `SRC_TO_DST_IAT_MIN`, `DST_TO_SRC_IAT_MIN` — 99.9% / 100.0% zero, no signal |
| **Sidecar only** | 0 | — every feature is at minimum in the sidecar ([§7](#7-sidecar-record)) |

`MAX_IP_PKT_LEN` is embedded but flagged: it duplicates `LONGEST_FLOW_PKT` in every sampled row. If a full-dataset check confirms exact equality, drop it from the text (not from the sidecar) and recover ~6 tokens.

### 5b. Tier 1 — core, 24-feature template

The fallback if [B10](#b10--the-full-fidelity-template-probably-does-not-fit-minilm) measures over budget. Eight lines, ~130–170 tokens estimated.

```
ALERT
Service: TCP port 445 microsoft-ds, source port 48171, app proto 11
Detector: Fuzzers score 0.72
Volume: in 4704 B 28 pkts, out 2976 B 28 pkts
Rate: in 112000 B/s, out 70857 B/s over 335 ms
Size: longest 984, shortest 52, buckets 34/18/2/2/0
TTL: min 31 max 32
Flags: tcp 27 client 27 server 27, window in 14480 out 14480
Timing: fwd iat max 91 avg 12, rev iat max 90 avg 12
```

Covers: 4 service + 4 volume + 2 throughput + 1 duration + 2 size + 5 histogram + 2 TTL + 3 flags + 2 window + 4 IAT = **29 features** across 8 lines. (Retransmission, ICMP, DNS, FTP, `DURATION_IN/OUT`, `MIN/MAX_IP_PKT_LEN`, IAT stddev drop out.)

### 5c. Tier 2 — full, 44-feature template

Preferred if the token budget allows. Fourteen lines.

```
ALERT
Service: TCP port 445 microsoft-ds, source port 48171, app proto 11
Detector: Fuzzers score 0.72
Volume: in 4704 B 28 pkts, out 2976 B 28 pkts
Duration: flow 335 ms, in 334 ms, out 334 ms
Rate: in 112000 B/s, out 70857 B/s
Size: longest 984, shortest 52, ip min 52 max 984
Shape: pkts 34 <=128, 18 128-256, 2 256-512, 2 512-1024, 0 1024-1514
TTL: min 31 max 32
Flags: tcp 27 client 27 server 27
Window: in 14480 out 14480
Retransmit: in 1988 B 7 pkts, out 1068 B 6 pkts
Timing: fwd iat max 91 avg 12 sd 19, rev iat max 90 avg 12 sd 19
App: icmp type n/a code n/a, dns qtype n/a ttl n/a, ftp rc n/a
```

This restores the axes analysts actually reason about, dilutes the detector label's lexical dominance (mitigating [B6](#b6--embedded-detector-label--label-based-retrieval--experimental-validity-risk)), and gives cosine similarity something structural to work with.

**Line order is fixed and part of the schema.** Reordering lines changes every embedding and is a `schema_version` bump.

### 5d. Open decision — magnitude tokens (D1)

MiniLM does not represent numeric magnitude well: `1840` and `184000` are unrelated tokens, so `IN_BYTES` contributes almost nothing to similarity as a bare integer ([R7](../docs/memory-layer/06-risks-and-limitations.md#r7--numeric-features-in-a-text-embedding-space)). The standard mitigation is a qualitative token alongside the number:

```
Volume: in 4704 B 28 pkts (medium), out 2976 B 28 pkts (medium)
```

**Recommendation:** apply it to the three highest-signal axes only — volume, rate, duration — using **fixed base-10 order-of-magnitude buckets** (`<1e2` tiny, `<1e4` small, `<1e6` medium, `<1e8` large, else huge). Fixed cutoffs, not quantiles fitted to the data: quantile buckets would be fitted on the dataset the experiment runs on, which is a subtle form of leakage and would have to be refitted on any dataset switch ([B8](#b8--the-two-nf-datasets-have-disjoint-label-vocabularies--new-created-by-the-b1-decision)).

Costs ~10 tokens. **Not implemented pending your decision** — it changes the embedding text for every case, so it must be settled before the store is built, not after.

### 5e. Three text surfaces, three budgets — do not conflate them

A recurring source of confusion: "the alert text" is not one thing. Three different strings exist, with different limits and different owners.

| Surface | Contents | Budget | Governed by |
|---|---|---|---|
| **Embedding document** | Core block only ([§5c](#5c-tier-2--full-44-feature-template)). No SHAP, no verdict, no precedent. | **256 tokens, hard** — silent truncation past it | this layer; [B10](#b10--token-budget--estimated-comfortable-confirm-with-the-real-tokenizer) |
| **LLM prompt (input)** | base template + Core block + `shap_explanation` + **(Arm B only)** retrieved precedent | thousands of tokens — not a constraint at k≤5 | Layer 4; template is a protected component |
| **LLM response (output)** | verdict, rationale, dual-audience summaries | whatever the output contract says | Layer 4 instructions |

Three consequences worth stating plainly:

1. **Strict LLM instructions do not help the embedding budget.** Output instructions constrain what the model *writes*; the 256-token limit applies to what the *embedder reads*, on a different string entirely. The two are unrelated.
2. **Arm B's prompt is necessarily longer than Arm A's** — it carries retrieved precedent, and that is the independent variable. This is expected, not a control violation. The base template and the instruction block must be **byte-identical** in both arms; only the injected precedent differs. Prompt length delta is itself a Phase 4 metric ("token cost overhead introduced by retrieval", [`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §7).
3. **A strict output contract is what makes [§6](#6-metadata) writable.** `verdict` must come back as a value from a closed vocabulary and `rationale_summary` must fit 500 characters, or the write path has to truncate or coerce — both of which corrupt what gets stored. Recommend the LLM return structured JSON with an explicit length cap on each free-text field, and that the write path **reject** a malformed response rather than repair it. A silently repaired verdict is an unlogged data mutation.

### Rendering rules

Carried over unchanged from [`02-case-schema.md §Rendering rules`](../docs/memory-layer/02-case-schema.md#rendering-rules) — fixed field order, every line always present, fixed decimal precision, `n/a` for null/NaN/Inf, resolved protocol and port names, no scaling, one shared `CaseRenderer` for both paths.

Three additions forced by this dataset:

1. **`inf` is real, not theoretical.** `SRC_TO_DST_SECOND_BYTES` / `DST_TO_SRC_SECOND_BYTES` are `inf` for zero-duration flows. They are excluded from the embedding text, but the sidecar writer and any metadata path must handle `inf` explicitly — JSON has no `Infinity` literal, and Chroma metadata rejects it. Serialize as the string `"inf"` in the sidecar; never store as a metadata float.
2. **Integer rendering is exact, never formatted.** No thousands separators, no scientific notation, no rounding — `112000`, not `1.12e5` or `112,000`. Float features (`L7_PROTO`, the two `*_SECOND_BYTES`) render to a fixed 2 decimal places.
3. **SHAP entry order must be explicitly sorted** (by `|shap_value|` descending) in the renderer, not inherited from the producer. See [B3](#b3--shap_explanation-is-not-reproducible-from-the-repo-).

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

### 6b. Flow-feature metadata (requires B7)

Metadata exists to be *filtered on* and *cited*, not to mirror the feature vector — that is the sidecar's job. Chroma supports numeric comparison operators (`$gt`, `$lte`, …), so the selection criterion is: **would a retrieval config or an analyst plausibly filter on this?** Fourteen of the 48 qualify.

| Key | Type | Feature | Why it earns a slot |
|---|---|---|---|
| `l7_proto` | float | `L7_PROTO` | Application protocol — the natural companion filter to `protocol` |
| `in_bytes` / `out_bytes` | int | `IN_BYTES` / `OUT_BYTES` | Range filters ("similar-volume precedent") |
| `in_pkts` / `out_pkts` | int | `IN_PKTS` / `OUT_PKTS` | Same |
| `flow_duration_ms` | int | `FLOW_DURATION_MILLISECONDS` | Range filter; separates scans from sessions |
| `tcp_flags` | int | `TCP_FLAGS` | nuniq 12 — effectively categorical, a strong exact-match filter |
| `min_ttl` / `max_ttl` | int | `MIN_TTL` / `MAX_TTL` | nuniq 10/13. ⚠️ **partial oracle on this dataset — see [B9](#b9--host-identity-is-a-perfect-ground-truth-oracle--do-not-embed-do-not-filter-on-it).** Store; do not put in a default retrieval filter. |
| `longest_flow_pkt` / `shortest_flow_pkt` | int | `LONGEST_FLOW_PKT` / `SHORTEST_FLOW_PKT` | Packet-size envelope |
| `retransmitted_in_pkts` / `retransmitted_out_pkts` | int | `RETRANSMITTED_{IN,OUT}_PKTS` | Retransmission is a distinct behavioural axis; zero in ~26% of flows, so a useful discriminator |
| `flow_start_ms` | int | dropped col | Ordering + audit only. Optional, blocked on Layer 2 change (3). Partial oracle — **do not filter on it** |

**No `src_ip` / `dst_ip`.** Excluded by decision, permanently — see [B9](#b9--host-identity-is-a-perfect-ground-truth-oracle--closed-2026-08-15--standing-constraint).

That is 14 flow keys on top of the ~17 in the table above: roughly **31 metadata keys per case**, all scalar. At 10k cases this is a few MB of SQLite — negligible.

**The other 34 features are sidecar-only.** They are still fully preserved, still available for post-hoc analysis, and still (mostly) in the embedding text; they just do not earn a filter slot.

**Enforcement:** the retriever must validate `where` keys against an allowlist at startup and refuse `flow_start_ms`, `min_ttl`, `max_ttl`, `detector_label`. A filter that silently makes retrieval an oracle is exactly the failure [`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §3 says invalidates the experiment.

**Deliberately absent: `ground_truth`.** Per [`PROJECT_BRIEF.md`](../PROJECT_BRIEF.md) §5 and [OQ-2](../docs/memory-layer/07-open-questions.md#oq-2--does-ground-truth-feed-the-memory-store), labels are the evaluation oracle and live in the scoring log, joined by `alert_id` after the run. [`CLAUDE.md`](../CLAUDE.md) reserves this question — it is not decided here in either direction.

**`top_features` is deliberately excluded** from both embedding text and metadata while B2 stands: a constant value has no filtering or retrieval utility.

---

## 7. Sidecar record

`artifacts/memory/<run_id>/cases.jsonl`, keyed by `case_id`. Holds the full untruncated rationale, both report views, **the complete flow feature vector as ingested**, the full `shap_explanation` array, all retrieval candidates with distances, and raw LLM token/latency metadata.

"Complete flow feature vector" now means something precise: **all 48 features of [§2b](#2b-the-feature-universe--verified), under their exact CSV column names, unrounded, unscaled, in CSV column order**, plus the five dropped columns where recoverable. This is what makes a stored case reconstructible and the run auditable; nothing here is selected or filtered. `inf` values serialize as the string `"inf"` (see rendering rule 1).

The complete SHAP array belongs here regardless of how B3 resolves — it is a list of dicts, which Chroma metadata cannot store, and it is never filtered on.

---

## 8. What Layer 2 must change

Ordered by value to this layer. **All of these are Layer 2 edits and out of scope for me** — flagged per [`CLAUDE.md`](../CLAUDE.md), not made.

| # | Change | Unblocks | Status |
|---|---|---|---|
| 1 | Emit a stable `alert_id` per alert | B4 — and Phase 4 scoring | 🔴 open |
| 2 | Pass through the **fixed 44-feature Core block** as values, not names | B7, B6, R7, B11 | 🔴 open — **the critical one** |
| 3 | Re-join `FLOW_START_MILLISECONDS` | timestamp metadata | 🟡 optional |
| 4 | Replace global `top_features` with per-sample SHAP | B2 | 🟠 partly done — `shap_explanation` is per-sample; `top_features` is still emitted alongside it and should be dropped |
| 5 | Emit `detector_version` | B5 | 🟡 open |
| 6 | Make `shap_explanation` reproducible with guaranteed ordering | B3 | ✅ **done** — `shap_explainer.py:136-141` |

On (2): [B11](#b11--shap-selected-features-make-the-alert-variable-shape--breaks-comparability) supersedes the earlier "10–15 features" wording. The block must be **fixed and complete**, not selected per alert. `main.py:401` already passes the entire flow row (`flow=sample.iloc[0]`) into `AlertGenerator.generate()`, which then keeps three fields — so this is a widening of the extraction at `alert_generator.py:19-21`, not new plumbing.

On (3): `FLOW_START_MILLISECONDS` is dropped from `X` at `feature_engineering.py:18-26`, but `X` is built via `self.df.drop(columns=...)`, which **preserves the index** — so it is recoverable by an index join against `df` without retraining or altering the frozen model. This does not touch detector weights or thresholds.

**Withdrawn:** the earlier request to re-join `IPV4_SRC_ADDR` / `IPV4_DST_ADDR`. See [B9](#b9--host-identity-is-a-perfect-ground-truth-oracle--closed-2026-08-15--standing-constraint) — they must never reach this layer.

---

## 9. Schema versioning

`schema_version` starts at `"0.1"` and is **provisional**. Any change to the template, field set, rounding, or label wording is a version bump, and a store may contain only one version ([`02-case-schema.md §Schema versioning`](../docs/memory-layer/02-case-schema.md#schema-versioning)).

Because B1–B7 will all change the template, **expect the schema to be re-versioned before Phase 2.** Do not treat `0.1` as lockable — building a large store against it now guarantees rework.
