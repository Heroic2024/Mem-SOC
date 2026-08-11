# 04 — Read Path

> Retrieval and prompt injection. Implements [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4 (Layer 3) and the tuning sweep in §7 Phase 3.

---

## Sequence

```
Alert
 1. CaseRenderer.to_query_text(alert)        same template as write
 2. EmbeddingFunction.encode(text)           same model as write — Invariant #1
 3. collection.query(query_embeddings=[v], n_results=k, where=filter,
                     include=["documents","metadatas","distances"])
 4. similarity = 1 - distance                cosine space
 5. drop cases with similarity < τ_read
 6. apply diversity constraint (if enabled)
 7. log all candidates + survivors
 8. return RetrievalResult
```

Steps 1 and 2 are the same code objects the write path uses. That is the mechanism, not a convention.

---

## Distance and similarity

Chroma returns **distances**, not similarities, and the meaning depends on the collection's configured space. With cosine space and L2-normalized embeddings:

```
similarity = 1 - distance        →  distance 0.0 = identical, 1.0 = orthogonal
```

Three things to get right:

- **Configure the space explicitly** as cosine when the collection is created. The default is L2, and L2 distance on normalized vectors is monotonically related to cosine but on a different scale — a threshold tuned under one is meaningless under the other. See [05](./05-configuration.md#distance-space).
- **Convert once, in one place.** A similarity computed differently in the retriever and in the logger will produce threshold behaviour nobody can reproduce.
- **Log both.** Distance is what Chroma gave you; similarity is what the threshold used. Logging only the derived value makes it impossible to detect a space misconfiguration after the fact.

---

## Parameters

| Parameter | Role | Sweep range (Phase 3) | Notes |
|---|---|---|---|
| `k` (top-k) | How many candidates to fetch | 1, 3, 5, 10 | Fetching more is cheap; *injecting* more costs tokens and dilutes attention. |
| `τ_read` | Minimum similarity to inject | 0.0, 0.5, 0.6, 0.7, 0.8, 0.9 | `0.0` = no threshold, the retrieval-noise worst case. Include it — it is the control that shows whether the threshold matters. |
| `where` | Metadata pre-filter | see below | Applied by Chroma before ranking. |
| diversity | Cap on near-identical hits | off, or max 2 per distinct flow | See below. |

`k` and `τ_read` interact and must be swept jointly, not one at a time. A large `k` with a high threshold behaves like a small `k`; a small `k` with no threshold guarantees noise injection whenever the store lacks anything relevant.

These are the **only** parameters this layer is permitted to tune. Detector thresholds and prompt wording are protected components and are not in the sweep ([`CLAUDE.md`](../../CLAUDE.md)).

### Metadata filters

Chroma applies `where` **before** similarity ranking, so a filter shrinks the candidate pool rather than reordering it.

**Defensible filters** (network-structural, no label leakage), assuming the fields survive Phase 0 preprocessing ([02 §The Layer 2 input contract](./02-case-schema.md#the-layer-2-input-contract)):

```python
{"protocol": alert.protocol}                                    # same transport
{"$and": [{"protocol": ...}, {"dst_port": alert.dst_port}]}     # same service
```

**Filters that would break the experiment:**

| Filter | Why it is disqualifying |
|---|---|
| any time-derived field | Testbed captures like the NF-* v3 datasets concentrate each attack family in specific capture windows. Filtering by time leaks the label through the filter. |
| `{"detector_label": ...}` | Restricts precedent to cases the frozen detector already agreed with, so memory can no longer contradict the detector — which is one of the things it is supposed to be able to do. |
| `{"verdict": "true_positive"}` | Retrieves only confirmations. Guarantees biased precedent. |
| anything derived from ground truth | The oracle leak from [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §5. |

**Default: no filter.** Pure similarity is the cleanest baseline and the easiest to defend. Filters are a Phase 3 variant, reported separately.

### Near-duplicate saturation

If the alert stream contains bursts of near-identical flows, top-*k* can return *k* copies of essentially the same case — effective *k* collapses to 1, and the prompt carries several redundant blocks paying several times the tokens for one piece of information. Worse, a wrong verdict inside a burst gets retrieved repeatedly, amplifying error propagation.

Options, in order of preference:

1. **Diversity cap** — fetch `k × 3` candidates, then keep at most *n* per distinct flow identity until *k* are selected. Preserves "this happened repeatedly" via a count, without spending the budget on it.
2. **Similarity ceiling** — drop candidates above ~0.99 similarity as trivially identical. Simple, but discards genuinely informative exact recurrences.
3. **Do nothing, and measure it.** Report mean pairwise similarity within retrieved sets. If saturation is severe, the diversity cap is justified by data rather than by assumption.

Start with (3) in Phase 2 so the baseline is unmodified, then adopt (1) in Phase 3 if the measurement supports it.

---

## Empty results and cold start

An empty `RetrievalResult` is a **normal state**, not an error. It occurs when:

- The store is empty (start of every run — [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §8 cold start).
- Nothing cleared `τ_read`.
- A `where` filter matched nothing.

**Required behaviour:** the prompt renders with no precedent block at all — byte-identical to the Arm A prompt. Not "no relevant past cases were found," which is itself an instruction to the LLM and a difference between arms. Silence, not a stated absence.

**Cold start is not a bug to be engineered away.** Early alerts genuinely have no precedent, and that is the honest behaviour of a memory system on its first shift. Two obligations:

1. **Log `collection_count` at every retrieval** so Phase 4 can split cold-start from steady-state performance — [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 Phase 3 requires reporting them separately if not warm-starting.
2. **If warm-starting, document the seed set's provenance.** A seed set built from ground-truth-labelled cases is the oracle leak wearing a different hat. See [OQ-4](./07-open-questions.md#oq-4--where-does-a-cold-start-seed-set-come-from).

A useful diagnostic: plot retrieval hit rate against `collection_count`. Where it plateaus is the empirical cold-start boundary, and that number belongs in the results.

---

## Prompt injection format

The retrieved cases are rendered into the **single shared prompt template** ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §9). The template is a protected component: one object, identical across arms, no per-arm wording. With an empty case list it must produce the Arm A prompt exactly.

```
Relevant past cases from this SOC's records:

[Case r7f3a1:000097 — similarity 0.87]
172.16.0.1:51204 -> 192.168.10.50:80 TCP port http
Detector: <label> score 0.88
Volume: 7 fwd / 6 bwd pkts, 1740 / 10982 bytes
Rate: 388 pkt/s, 1021440 B/s over 31 ms
Verdict: true_positive (confidence 0.91)
Reasoning: Sustained high-rate HTTP exchange with 6:1 down/up ratio to a web server.

[Case r7f3a1:000201 — similarity 0.79]
...
```

Rules:

- **Ordered by descending similarity.** Most relevant first.
- **Similarity is shown to the LLM.** It should be able to weight a 0.62 match differently from a 0.94 match. This is also what makes "why was this precedent relevant" answerable in the report ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4, Layer 4).
- **Case IDs are shown.** The report must cite which past cases it matched; the LLM cannot cite an ID it was never given.
- **Rationale is truncated** to the `rationale_summary` (≤500 chars), not the full sidecar text. Full rationales at k=5 would dominate the context.
- **Token budget is enforced.** Cap the precedent block; drop the lowest-similarity cases first, and log every drop. A silently truncated prompt is an unrecorded change to the experimental condition.
- **The precedent block is framed as records, not as instructions.** "Relevant past cases from this SOC's records" — not "these cases were previously confirmed correct." The stored verdicts may be wrong; that is the entire error-propagation question, and the framing must not pre-empt it.
- **Wording changes here are prompt-template changes.** They affect Arm B only and therefore require the same care as any protected-component change — raise before editing.

---

## Latency and token accounting

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 Phase 4 makes retrieval overhead a reported metric, so it must be instrumented at the source rather than inferred.

Per retrieval, record:

| Field | Meaning |
|---|---|
| `embed_ms` | Query embedding time |
| `query_ms` | Chroma search time |
| `total_retrieval_ms` | Steps 1–8 |
| `collection_count` | Store size at query time — retrieval cost is a function of this |
| `candidates_returned` | Before thresholding |
| `candidates_injected` | After thresholding and diversity |
| `precedent_tokens` | Tokens added to the prompt by the precedent block |

`precedent_tokens` is the honest token-overhead number: it is the difference between the Arm B and Arm A prompts for the same alert, and it should be computed that way rather than estimated.

Arm A logs zeros for all of these — not nulls. Zeros make the comparison a straight subtraction and keep the log schema identical across arms.

---

## Retrieval quality audit

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 Phase 3 requires verifying that retrieved cases are "genuinely relevant, not noise," and Phase 4 makes rationale quality a reported metric. Similarity scores alone cannot establish this — a high cosine score between two rendered flow descriptions is evidence about text, not about security relevance.

**Manual audit protocol:** sample ~50 retrievals stratified across similarity bands (0.5–0.6, 0.6–0.7, 0.7–0.8, 0.8–0.9, 0.9+). For each, rate the top hit as *relevant* / *superficially similar* / *irrelevant*, blind to the verdict. This gives an empirical relevance-versus-similarity curve, and **that curve is what should set τ_read** — a threshold picked by intuition is not defensible in the writeup.

**Automated proxies** (cheap, run over the whole set, but weaker evidence):

- Agreement between the retrieved case's `detector_label` and the query alert's — high agreement suggests structural relevance.
- Post-hoc ground-truth agreement between retrieved cases and the query alert, computed **in the scoring harness only, after the run**. This is a legitimate use of the oracle: it evaluates retrieval without ever exposing labels to the system.
- Mean pairwise similarity within retrieved sets — the saturation diagnostic above.

Report the relevance curve alongside the chosen `τ_read`. If retrieval turns out to be mostly noise above the threshold, Arm B underperforming Arm A is explained rather than mysterious — and [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §8 is explicit that a negative result is a legitimate outcome.
