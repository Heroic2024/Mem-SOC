# 02 — Case Schema

> Addresses the Phase 0 task in [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7: *"Define the case schema: which features become the embedded text representation vs. which become filterable metadata."*
>
> **Status: proposal, not settled.** [`CLAUDE.md`](../../CLAUDE.md) forbids inventing dataset fields or schema entries. Every field below is either derived from a decision already made in [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md), or marked **pending** because it depends on a Phase 0 decision that has not been taken. Nothing here is locked until the open questions close.

---

## The three-way split

A stored case is not one blob. It has three parts with three different jobs.

| Part | Chroma field | Job | Consequence of getting it wrong |
|---|---|---|---|
| **Embedding text** | `documents` | Determines *what similar means* | Bad similarity; retrieval returns noise |
| **Metadata** | `metadatas` | Determines *what can be filtered and cited* | Cannot filter; cannot cite case IDs |
| **Sidecar record** | external JSONL | Full rationale, full feature vector, audit trail | Bloated store; slow queries; nothing lost analytically |

Chroma embeds the `documents` field. Everything in it shapes the vector. Everything *not* in it is invisible to similarity — retrievable and filterable, but not part of the match.

---

## The Layer 2 input contract

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 Phase 0 requires *"find the right OS ML model and define the output format"* and that *"complete data consistency should be maintained between layers."* **That decision has not been made.** Until it is, this schema cannot be locked, because several of its fields are inherited directly from the detector.

What the memory layer **requires** from Layer 2, stated model-agnostically:

| Requirement | Why the memory layer needs it |
|---|---|
| A **stable label** per alert, drawn from a closed, documented vocabulary | Becomes `detector_label`; rendered into the embedding text; the most semantically meaningful token in an otherwise numeric record |
| A **confidence or score** per alert | Becomes `detector_score`; rendered into the text and available to write policies |
| A **version identifier** for the frozen detector | Becomes `detector_version`; makes an accidental detector change detectable after the fact |
| The **feature set** that survives preprocessing, and its column names | Determines what the embedding template can actually render — see below |
| Stable **alert identity** across the stream | Lets a case in memory be joined back to its alert, its ground-truth label, and its scoring record |

Two consequences worth stating plainly:

- **A detector that emits only a predicted class, with no confidence exposed, is insufficient for this layer as designed.** `detector_score` appears in the embedding template and gates the `confidence_gated` write policy ([03](./03-write-path.md#confidence_gated--store-only-above-a-confidence-floor)). If the chosen detector's interface does not surface a score, either the interface must expose one or those two uses must be removed — a decision, not an implementation detail.
- **The embedding template can only render fields that survive preprocessing.** If the Phase 0 preprocessing drops identity columns (addresses, ports, protocol, timestamps) and keeps only numeric flow statistics, the template below loses its most semantically meaningful lines and similarity becomes almost entirely numeric — which materially worsens [R7](./06-risks-and-limitations.md#r7--numeric-features-in-a-text-embedding-space). See [OQ-9](./07-open-questions.md#oq-9--what-does-layer-2-emit).

Fields below inherited from this contract are marked **pending**.

---

## Part 1 — Embedding text

### The symmetry requirement

The read path embeds an **alert** (no verdict, no rationale — it hasn't been triaged yet). The write path embeds a **case** (alert + verdict + rationale). If the write path embeds text containing a `VERDICT:` line and the read path embeds text that does not, query and document vectors live in systematically different regions of the space, and cosine similarity degrades.

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4 (Layer 3) is inconsistent on exactly this point — its write-path bullet says embed "alert features + context + verdict + rationale", its read-path bullet says embed "the incoming alert". **This is [OQ-1](./07-open-questions.md#oq-1--does-the-embedded-text-include-the-verdict) and needs a team decision.**

The schema below assumes the **symmetric option**: the embedded text describes the alert only. Verdict and rationale are stored as metadata and sidecar, retrieved with the case, and injected into the prompt — they are simply not part of what determines the match. This is recommended because *"find alerts that look like this one"* is the retrieval semantics the system actually wants, and it keeps query and document identically shaped.

If the team chooses otherwise, `CaseRenderer` must render a synthetic verdict placeholder on the query side, and that decision must be recorded here.

### Feature selection

The NF-* v3 datasets carry 55 columns — 53 flow features plus `Label` and `Attack`; 48 features survive into `X` after the drops at `src/memsoc/detection/features/feature_engineering.py:18-26`. Embedding all of them is counterproductive:

- **Token budget.** The candidate embedding model truncates at a fixed sequence length (256 word-piece tokens for `all-MiniLM-L6-v2`, the model named as a candidate in [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §6). Dozens of labelled float values overrun it, and the model silently drops the tail — the last third of the features then contribute *nothing*, unpredictably. See [05 §Token budget](./05-configuration.md#token-budget) and [R5](./06-risks-and-limitations.md#r5--silent-truncation-at-the-token-limit).
- **Signal dilution.** Sentence-transformer embeddings of long numeric strings compress toward each other. More numbers is not more signal.
- **Redundancy.** Many NF-* v3 features are near-collinear (the `NUM_PKTS_*_BYTES` buckets, the paired `SRC_TO_DST_*` / `DST_TO_SRC_*` statistics).

The template below covers the axes SOC analysts actually reason about: who talked to whom, volume, rate, shape, timing, and TCP flag posture. **Which of these fields actually exist is pending** the Phase 0 preprocessing decision ([OQ-9](./07-open-questions.md#oq-9--what-does-layer-2-emit)).

### Template — draft, pending OQ-9

```
ALERT {day} {timestamp}
{src_ip}:{src_port} -> {dst_ip}:{dst_port} {protocol_name} port {dst_port_name}
Detector: {detector_label} score {detector_score:.2f}
Volume: {total_fwd_packets} fwd / {total_bwd_packets} bwd pkts, {total_len_fwd} / {total_len_bwd} bytes
Rate: {flow_packets_per_s:.0f} pkt/s, {flow_bytes_per_s:.0f} B/s over {flow_duration_ms:.0f} ms
Size: fwd mean {fwd_pkt_len_mean:.0f} max {fwd_pkt_len_max:.0f}, bwd mean {bwd_pkt_len_mean:.0f} max {bwd_pkt_len_max:.0f}
Timing: IAT mean {flow_iat_mean:.0f} std {flow_iat_std:.0f}, idle mean {idle_mean:.0f}
Flags: SYN {syn} FIN {fin} RST {rst} PSH {psh} ACK {ack} URG {urg}
Shape: down/up {down_up_ratio}, avg pkt {avg_packet_size:.0f}, init win {init_win_fwd}/{init_win_bwd}
```

Nine lines, roughly 120–160 word-piece tokens depending on value widths — inside a 256-token limit with headroom, but this must be **measured, not assumed** ([05 §Token budget](./05-configuration.md#token-budget)).

Lines 1 and 2 depend entirely on identity columns surviving preprocessing. If they do not, the template degrades to seven numeric lines, and the two most human-meaningful signals — the service being talked to and the transport — are gone. Flag this to the Layer 2 decision rather than silently dropping the lines.

### Rendering rules

These are not cosmetic. They control variance in the vector space.

| Rule | Why |
|---|---|
| **Fixed field order, fixed labels, every line always present** | Positional and lexical consistency. A missing line shifts everything after it. |
| **Fixed decimal precision per field** (as in the template) | `1523.4471028` and `1523.4` embed differently. Round once, at render time. |
| **Render `null`/`NaN`/`Inf` as the literal `n/a`** | The NF-* v3 rate/throughput columns contain non-finite or missing values for zero-duration flows — `SRC_TO_DST_SECOND_BYTES` is explicitly null-filled at `preprocessor.py:30-32`. Never render `inf` or let a formatter raise. |
| **Resolve protocol number to name** (`6`→`TCP`, `17`→`UDP`) | Gives the language model something semantically meaningful to match on. |
| **Resolve well-known destination ports to a name** (`80`→`http`, `443`→`https`, `22`→`ssh`; otherwise the number) | Same reason. `ssh` carries meaning that `22` does not. |
| **Do not normalize or scale numerics** | Scaling is for the detector, not for text. Human-readable magnitudes embed better. |
| **Same template on both paths, same code** | Invariant #4. `CaseRenderer` is the only implementation. |

---

## Part 2 — Metadata

Stored in Chroma, filterable via `where`, returned with every hit, cited in reports.

**Chroma constraint:** metadata values must be `str`, `int`, `float`, or `bool`. No `None`, no lists, no nested dicts. Use sentinels (`"unknown"`, `-1`) rather than omitting keys — a key present on some cases and absent on others makes `where` filters behave inconsistently.

### Identity and provenance

| Key | Type | Example | Purpose |
|---|---|---|---|
| `case_id` | str | `r7f3a1:000412` | Primary key. Cited in reports. |
| `run_id` | str | `r7f3a1` | Which run wrote this case. |
| `seq` | int | `412` | Position in the replay stream. Enables "what did memory know at alert *n*". |
| `alert_id` | str | `r7f3a1:000412` | Links to the alert record in the run log. |
| `created_at` | str | `2026-07-31T11:54:03Z` | Wall-clock write time. |
| `schema_version` | str | `1.0` | Cases rendered under different templates are not comparable. Bump on any template change. |

`case_id` is `{run_id}:{seq:06d}` — deterministic, sortable, collision-free within a run, and immediately traceable. Do not use a random UUID; a case ID that cannot be traced back to a stream position is not citable in an audit.

A dataset-native flow identifier should also be stored if one survives preprocessing, so cases can be joined back to the source data. **Pending** [OQ-9](./07-open-questions.md#oq-9--what-does-layer-2-emit).

### Network context — pending OQ-9

Every key here exists only if the corresponding column survives Phase 0 preprocessing.

| Key | Type | Filterable use |
|---|---|---|
| `src_ip` | str | Rare. Same-host precedent. |
| `src_port` | int | Low value; ephemeral. |
| `dst_ip` | str | Same-target precedent. |
| `dst_port` | int | **High value.** Service-scoped precedent. |
| `protocol` | int | **High value.** Numeric, as in the dataset. |
| `protocol_name` | str | Human-readable mirror, for reports. |
| `day` | str | Capture day. Useful for slicing, **dangerous as a filter** — see below. |
| `timestamp` | str | Flow timestamp from the dataset. |

> **Do not filter on any time-derived field in the retrieval path.** In testbed captures like the NF-* v3 datasets, attack families are concentrated in specific capture windows. Filtering by capture day or time range would leak the label through the filter and hand Arm B an advantage that has nothing to do with memory. Store time for post-hoc analysis only. Note that any such field would have to be derived from `FLOW_START_MILLISECONDS`, which is currently dropped before the alert is built (`feature_engineering.py:23-24`).

### Detector output — pending OQ-9

| Key | Type | Notes |
|---|---|---|
| `detector_label` | str | The frozen detector's predicted class. Vocabulary is whatever Layer 2 defines. |
| `detector_score` | float | Confidence. **Requires the detector interface to expose one** — see [§The Layer 2 input contract](#the-layer-2-input-contract). |
| `detector_version` | str | Constant across a run; recorded so a detector change is detectable. |

### Triage output (Layer 4)

| Key | Type | Values | Notes |
|---|---|---|---|
| `verdict` | str | `true_positive` \| `false_positive` \| `inconclusive` | Closed vocabulary. Parsed and validated, never free text. Must match whatever the Phase 4 metric definitions expect — those are a protected component and are not adjusted to suit this schema. |
| `attack_category` | str | closed vocabulary + `none` / `unknown` | **Provenance is [OQ-3](./07-open-questions.md#oq-3--where-does-attack_category-come-from); the vocabulary itself is pending the Phase 0 label-set decision.** Do not invent one here. |
| `confidence` | float | `0.0`–`1.0` | LLM-reported. Gates confidence-based write policies. |
| `rationale_summary` | str | ≤ 500 chars | Truncated. Full text in the sidecar. |
| `precedent_used` | str | `r7f3a1:000097,r7f3a1:000201` or `""` | Comma-joined case IDs that informed *this* verdict. Chroma forbids lists. |
| `precedent_count` | int | `2` | Convenience mirror of the above. |

`precedent_used` is what makes error propagation traceable. Without it you can observe that memory degraded results but not trace the chain that did it. It is not optional.

### The `attack_category` problem

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4 (Layer 3) lists "attack category" as stored metadata but never says where it comes from. Three candidates, not equivalent:

1. **The detector's predicted class** — safe, no leakage, but already captured as `detector_label`.
2. **The LLM's own categorization** — safe; a model output, so it can be wrong, which is acceptable and informative.
3. **The dataset's ground-truth label** — **this leaks the oracle into memory** and would inflate Arm B's results. It is the contamination [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §5 warns about.

The schema above assumes **(2)**. See [OQ-3](./07-open-questions.md#oq-3--where-does-attack_category-come-from).

### Deliberately absent: ground truth

There is **no `ground_truth` key** in this schema. Ground-truth labels are the evaluation oracle ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §5) and live in the scoring log, joined to cases by `alert_id` after the run. Putting them in the vector store would make memory an oracle rather than an analyst record.

[`CLAUDE.md`](../../CLAUDE.md) states this question is **open** and that neither interpretation may be implemented without confirmation. The absence above is the working assumption from §5, not a decision. See [OQ-2](./07-open-questions.md#oq-2--does-ground-truth-feed-the-memory-store).

---

## Part 3 — Sidecar record

Written to `data/memory/<run_id>/cases.jsonl`, keyed by `case_id`. Not in Chroma.

Holds: the full untruncated rationale, both the technical and non-technical report views, the complete feature vector as ingested, the full retrieval result that informed the verdict (all candidates with distances, not just survivors), and raw LLM response metadata (token counts, latency).

**Why separate.** Chroma metadata is loaded into memory with the collection — high memory usage at scale is a documented limitation ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §6). Storing multi-kilobyte rationales and full feature vectors per case as metadata inflates the resident footprint for data that is never filtered on. The sidecar keeps the store lean and loses nothing: every analytical question can be answered by joining on `case_id`.

The sidecar is also the only safe path to a template change ([§Schema versioning](#schema-versioning)) — it holds everything needed to re-render cases without deleting anything.

---

## Illustrative example

**Values are placeholders.** The detector label and score come from a Layer 2 contract that does not exist yet, and the identity lines assume columns that may not survive preprocessing. This shows the *shape* of a case, not a real one.

**Embedding text** (this is what becomes the vector):

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

**Metadata:**

```json
{
  "case_id": "r7f3a1:000412", "run_id": "r7f3a1", "seq": 412,
  "alert_id": "r7f3a1:000412",
  "created_at": "2026-07-31T11:54:03Z", "schema_version": "1.0",
  "src_ip": "172.16.0.1", "src_port": 54312,
  "dst_ip": "192.168.10.50", "dst_port": 80,
  "protocol": 6, "protocol_name": "TCP",
  "day": "Wednesday", "timestamp": "2017-07-05T09:12:44",
  "detector_label": "<label>", "detector_score": 0.91, "detector_version": "<pending>",
  "verdict": "true_positive", "attack_category": "<pending>", "confidence": 0.88,
  "rationale_summary": "High bytes/s with sustained ACK-PSH exchange to port 80 and a 6:1 down/up ratio. Matches prior cases against the same host.",
  "precedent_used": "r7f3a1:000097,r7f3a1:000201", "precedent_count": 2
}
```

**Sidecar** (`cases.jsonl`): full rationale, both report views, the full feature vector, all retrieval candidates with distances, token counts, latency.

---

## Schema versioning

`schema_version` exists because **a template change invalidates every vector already in the store.** Text rendered under template 1.0 and text rendered under 1.1 do not occupy the same space, and mixing them silently corrupts similarity.

Rules:

- Any change to the embedding template, the field set, the rounding, or the label wording is a version bump.
- A store containing more than one `schema_version` is invalid. `MemoryStore` refuses to write a case whose version does not match the version already present in the collection.
- After a bump, **write a new run store** and re-render from the sidecar into it. Do **not** delete or regenerate the existing store — it is a protected component ([`CLAUDE.md`](../../CLAUDE.md)), and superseding it with a new directory achieves the same result without destroying anything. Never migrate in place.
- Changes to *metadata-only* fields do not require a bump, because they do not affect vectors — but they do require noting here.
