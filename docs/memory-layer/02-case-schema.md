# 02 — Case Schema

> Resolves the Phase 0 task in [`CLAUDE.md`](../../CLAUDE.md) §105: *"which features become the embedded text representation vs. which become filterable metadata."*
>
> This document proposes a concrete schema and flags the decisions it cannot make unilaterally.

---

## The three-way split

A stored case is not one blob. It has three parts with three different jobs.

| Part | Chroma field | Job | Consequence of getting it wrong |
|---|---|---|---|
| **Embedding text** | `documents` | Determines *what similar means* | Bad similarity; retrieval returns noise |
| **Metadata** | `metadatas` | Determines *what can be filtered and cited* | Cannot filter by protocol/verdict; cannot cite case IDs |
| **Sidecar record** | external JSONL | Full rationale, full feature vector, audit trail | Bloated store; slow queries; nothing lost analytically |

Chroma embeds the `documents` field. Everything in it shapes the vector. Everything *not* in it is invisible to similarity — retrievable and filterable, but not part of the match.

---

## Part 1 — Embedding text

### The symmetry requirement

The read path embeds an **alert** (no verdict, no rationale — it hasn't been triaged yet). The write path embeds a **case** (alert + verdict + rationale). If the write path embeds text containing a `VERDICT:` line and the read path embeds text that does not, query and document vectors live in systematically different regions of the space, and cosine similarity degrades.

[`CLAUDE.md`](../../CLAUDE.md) §66 and §67 are inconsistent on exactly this point — §66 says embed "alert features + context + verdict + rationale", §67 says embed "the incoming alert". **This is [OQ-1](./07-open-questions.md#oq-1--does-the-embedded-text-include-the-verdict) and needs a team decision.**

The schema below assumes the **symmetric option**: the embedded text describes the alert only. Verdict and rationale are stored as metadata and sidecar, retrieved with the case, and injected into the prompt — they are simply not part of what determines the match. This is recommended because *"find alerts that look like this one"* is the retrieval semantics the system actually wants, and it keeps query and document identically shaped.

If the team chooses otherwise, `CaseRenderer` must render a synthetic verdict placeholder on the query side, and that decision must be recorded here.

### Feature selection

CICIDS2017 ships ~78 numeric flow features. Embedding all of them is counterproductive:

- **Token budget.** `all-MiniLM-L6-v2` truncates at 256 word-piece tokens. 78 labelled float values blow past that, and the model silently drops the tail — meaning the last third of the features would contribute *nothing*, unpredictably. See [05 — Configuration](./05-configuration.md#token-budget).
- **Signal dilution.** Sentence-transformer embeddings of long numeric strings compress toward each other. More numbers is not more signal.
- **Redundancy.** Many CICIDS2017 features are near-collinear (`Subflow Fwd Bytes` ≈ `Total Length of Fwd Packets` for single-subflow flows).

The curated subset below covers the discriminative axes SOC analysts actually reason about: who talked to whom, volume, rate, shape, timing, and TCP flag posture.

### Template

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

Nine lines, ~120–160 word-piece tokens depending on value widths. Comfortably inside the 256 limit with headroom for IPv4 addresses tokenizing badly.

### Rendering rules

These are not cosmetic. They control variance in the vector space.

| Rule | Why |
|---|---|
| **Fixed field order, fixed labels, every line always present** | Positional and lexical consistency. A missing line shifts everything after it. |
| **Fixed decimal precision per field** (as in the template) | `1523.4471028` and `1523.4` embed differently. Round once, at render time. |
| **Render `null`/`NaN`/`Inf` as the literal `n/a`** | CICIDS2017 contains `Infinity` and `NaN` in `Flow Bytes/s` and `Flow Packets/s` for zero-duration flows. Never render `inf` or let a formatter crash. |
| **Resolve protocol number to name** (`6`→`TCP`, `17`→`UDP`, `0`→`HOPOPT`) | Gives the language model something semantically meaningful to match on. |
| **Resolve well-known destination ports to a name** (`80`→`http`, `443`→`https`, `22`→`ssh`, `21`→`ftp`, `53`→`dns`; otherwise the number) | Same reason. `ssh` carries meaning that `22` does not. |
| **Do not normalize or scale numerics** | Scaling is for the detector, not for text. Human-readable magnitudes embed better. |
| **Same template on both paths, same code** | Invariant #4. `CaseRenderer` is the only implementation. |

---

## Part 2 — Metadata

Stored in Chroma, filterable via `where`, returned with every hit, cited in reports.

**Chroma constraint:** metadata values must be `str`, `int`, `float`, or `bool`. No `None`, no lists, no nested dicts. Use sentinels (`"unknown"`, `-1`) rather than omitting keys — a key that is present on some cases and absent on others makes `where` filters behave inconsistently.

### Identity and provenance

| Key | Type | Example | Purpose |
|---|---|---|---|
| `case_id` | str | `r7f3a1:000412` | Primary key. Cited in reports. |
| `run_id` | str | `r7f3a1` | Which run wrote this case. |
| `seq` | int | `412` | Position in the replay stream. Enables "what did memory know at alert *n*". |
| `alert_id` | str | `r7f3a1:000412` | Links to the alert record in the run log. |
| `flow_id` | str | `192.168.10.5-...` | Dataset-native flow identifier. Links back to CICIDS2017. |
| `created_at` | str | `2026-07-28T11:54:03Z` | Wall-clock write time. |
| `schema_version` | str | `1.0` | Cases rendered under different templates are not comparable. Bump on any template change. |

`case_id` is `{run_id}:{seq:06d}` — deterministic, sortable, collision-free within a run, and immediately traceable. Do not use a random UUID; a case ID that cannot be traced back to a stream position is not citable in an audit.

### Network context

| Key | Type | Example | Filterable use |
|---|---|---|---|
| `src_ip` | str | `192.168.10.8` | Rare. Same-host precedent. |
| `src_port` | int | `54321` | Low value; ephemeral. |
| `dst_ip` | str | `205.174.165.73` | Same-target precedent. |
| `dst_port` | int | `80` | **High value.** Service-scoped precedent. |
| `protocol` | int | `6` | **High value.** Numeric, as in the dataset. |
| `protocol_name` | str | `TCP` | Human-readable mirror, for reports. |
| `day` | str | `Wednesday` | CICIDS2017 capture day. Useful for slicing, **dangerous as a filter** — see below. |
| `timestamp` | str | `2017-07-05T09:12:44` | Flow timestamp from the dataset. |

> **Do not filter on `day` in the retrieval path.** In CICIDS2017 each attack family is concentrated on specific capture days. Filtering by day would leak the label through the filter and hand Arm B an advantage that has nothing to do with memory. Store it for post-hoc analysis only.

### Detector output (Layer 2)

| Key | Type | Example | Notes |
|---|---|---|---|
| `detector_label` | str | `DDoS` | The frozen classifier's predicted class. |
| `detector_score` | float | `0.94` | Confidence/probability. |
| `detector_version` | str | `rf-v1` | Must be constant across a run; recorded so a detector swap is detectable. |

### Triage output (Layer 4)

| Key | Type | Values | Notes |
|---|---|---|---|
| `verdict` | str | `true_positive` \| `false_positive` \| `inconclusive` | Closed vocabulary. Parsed and validated, never free text. |
| `attack_category` | str | closed vocabulary, or `none` / `unknown` | **Provenance is [OQ-3](./07-open-questions.md#oq-3--where-does-attack_category-come-from).** |
| `confidence` | float | `0.0`–`1.0` | LLM-reported. Gates confidence-based write policies. |
| `rationale_summary` | str | ≤ 500 chars | Truncated. Full text in the sidecar. |
| `precedent_used` | str | `r7f3a1:000097,r7f3a1:000201` or `""` | Comma-joined case IDs that informed *this* verdict. Chroma forbids lists. |
| `precedent_count` | int | `2` | Convenience mirror of the above. |

`precedent_used` is what makes error propagation traceable. Without it you can observe that memory degraded results but not trace the chain that did it. It is not optional.

### The `attack_category` problem

[`CLAUDE.md`](../../CLAUDE.md) §66 lists "attack category" as stored metadata but never says where it comes from. There are three candidates and they are not equivalent:

1. **The detector's predicted class** — safe, already an input, no leakage.
2. **The LLM's own categorization** — safe, but it is a model output and can be wrong, which is fine (that is the point) but must be labelled as such.
3. **The CICIDS2017 ground-truth label** — **this leaks the oracle into memory** and would inflate Arm B's results. It is the failure mode [`CLAUDE.md`](../../CLAUDE.md) §87 warns about.

The schema above assumes **(2)**, with **(1)** already captured separately as `detector_label`. See [OQ-3](./07-open-questions.md#oq-3--where-does-attack_category-come-from).

### Deliberately absent: ground truth

There is **no `ground_truth` key** in this schema. Ground-truth labels are the evaluation oracle ([`CLAUDE.md`](../../CLAUDE.md) §85) and live in the scoring log, joined to cases by `alert_id` after the run. Putting them in the vector store would make memory an oracle rather than an analyst record. See [OQ-2](./07-open-questions.md#oq-2--does-ground-truth-feed-the-memory-store).

---

## Part 3 — Sidecar record

Written to `data/memory/<run_id>/cases.jsonl`, keyed by `case_id`. Not in Chroma.

Holds: the full untruncated rationale, both the technical and non-technical report views, the complete 78-feature vector as ingested, the full retrieval result that informed the verdict (all candidates with distances, not just survivors), and raw LLM response metadata (token counts, latency).

**Why separate.** Chroma metadata is loaded into memory with the collection ([`CLAUDE.md`](../../CLAUDE.md) §98 — high memory usage at scale is a documented limitation). Storing multi-kilobyte rationales and 78-float vectors per case as metadata inflates the resident footprint for data that is never filtered on. The sidecar keeps the store lean and loses nothing: every analytical question can be answered by joining on `case_id`.

---

## Worked example

**Input** — CICIDS2017 flow, Wednesday capture, flagged by the detector:

**Embedding text** (this is what becomes the vector):

```
ALERT Wednesday 2017-07-05T09:12:44
172.16.0.1:54312 -> 192.168.10.50:80 TCP port http
Detector: DoS Hulk score 0.91
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
  "flow_id": "172.16.0.1-192.168.10.50-54312-80-6",
  "created_at": "2026-07-28T11:54:03Z", "schema_version": "1.0",
  "src_ip": "172.16.0.1", "src_port": 54312,
  "dst_ip": "192.168.10.50", "dst_port": 80,
  "protocol": 6, "protocol_name": "TCP",
  "day": "Wednesday", "timestamp": "2017-07-05T09:12:44",
  "detector_label": "DoS Hulk", "detector_score": 0.91, "detector_version": "rf-v1",
  "verdict": "true_positive", "attack_category": "dos", "confidence": 0.88,
  "rationale_summary": "High bytes/s with sustained ACK-PSH exchange to port 80 and a 6:1 down/up ratio, consistent with HTTP flood. Matches prior confirmed DoS Hulk cases against the same host.",
  "precedent_used": "r7f3a1:000097,r7f3a1:000201", "precedent_count": 2
}
```

**Sidecar** (`cases.jsonl`): full rationale, both report views, all 78 features, all 5 retrieval candidates with distances, token counts, latency.

---

## Schema versioning

`schema_version` exists because **a template change invalidates every vector already in the store.** Text rendered under template 1.0 and text rendered under 1.1 do not occupy the same space, and mixing them silently corrupts similarity.

Rules:

- Any change to the embedding template, the field set, the rounding, or the label wording is a version bump.
- A store containing more than one `schema_version` is invalid. The `MemoryStore` should refuse to write a case whose version does not match the version already present in the collection.
- After a bump, re-render and re-embed from the sidecar, or drop and rebuild the store. Never migrate in place.
- Changes to *metadata-only* fields do not require a bump, because they do not affect vectors — but they do require noting here.
