# 03 — Write Path

> The write-back loop. Implements [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §4 (Layer 3) and the write-policy decision deferred to §7 Phase 3.

---

## When a write happens

Exactly once per alert, in Arm B only, **after** the verdict has been produced and logged for scoring.

```
verdict produced
  → verdict written to the scoring log        ← evaluation record is now safe
  → WritePolicy.should_write(case)
  → if allowed: render, embed, add to collection
  → outcome (written | rejected + reason) appended to the write log
```

Ordering matters. If the write ran before the verdict was logged, a store failure mid-run could lose a verdict from the evaluation. The scoring record must never depend on the memory layer succeeding.

**Arm A performs no write.** `NullMemoryLayer.write()` returns immediately without rendering, embedding, or touching disk. [`CLAUDE.md`](../../CLAUDE.md) requires this be verified before any baseline run — see [01 §Verifying the baseline never writes](./01-architecture.md#verifying-the-baseline-never-writes).

---

## What is written

One Chroma record per accepted case:

| Chroma field | Content |
|---|---|
| `ids` | `case_id` — `{run_id}:{seq:06d}` |
| `documents` | The rendered embedding text ([02 §Part 1](./02-case-schema.md#part-1--embedding-text)) |
| `embeddings` | Vector from the shared embedding function |
| `metadatas` | The metadata dict ([02 §Part 2](./02-case-schema.md#part-2--metadata)) |

Plus one line appended to `cases.jsonl` (the sidecar), always — **even when the write policy rejects the case.** A rejected case is still a data point: knowing what memory *declined* to learn is necessary to interpret why it behaved as it did.

Pass embeddings explicitly rather than letting Chroma call its own embedding function. It makes the shared-model invariant visible in the code instead of implicit in collection configuration.

---

## Write policies

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 Phase 3 assigns the write-policy decision to tuning and states it "directly controls error-propagation risk." Phase 2 needs a working default before that sweep exists — see [OQ-5](./07-open-questions.md#oq-5--what-is-the-phase-2-default-write-policy).

Policies are pluggable, share the same interface, and differ only in `should_write`.

### `write_all` — store every triaged case

```python
def should_write(case) -> tuple[bool, str]:
    return True, "write_all"
```

- **Models:** an analyst who documents every case, right or wrong.
- **Error propagation risk:** maximum. Every mistake becomes retrievable precedent.
- **Cold start:** fastest recovery — memory fills at one case per alert.
- **Recommended as the Phase 2 default.** It is the honest baseline: it makes error propagation *observable* rather than suppressed, and error propagation is a phenomenon this project exists to measure ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §8). Starting with a filtered policy would hide the effect and then require justifying the filter.

### `confidence_gated` — store only above a confidence floor

```python
def should_write(case) -> tuple[bool, str]:
    if case.confidence < threshold:
        return False, f"confidence {case.confidence:.2f} < {threshold}"
    return True, "confidence_gated"
```

- **Models:** an analyst who documents only cases they are sure about.
- **Error propagation risk:** reduced, **not eliminated** — a confidently wrong LLM verdict passes the gate. This is the important caveat: LLM confidence is self-reported and correlates imperfectly with correctness. Do not describe this policy as "prevents error propagation."
- **Cold start:** slower fill, and biased — memory over-represents easy cases, so precedent is least available exactly where it would help most.
- **Sweep range:** τ_write ∈ {0.6, 0.7, 0.8, 0.9}.
- **Note:** if gated on `detector_score` rather than the LLM's `confidence`, this depends on the detector exposing a score at all — see [02 §The Layer 2 input contract](./02-case-schema.md#the-layer-2-input-contract).

### `confirmed_only` — store only externally confirmed verdicts

- **Models:** a curated knowledge base with an analyst review step.
- **Error propagation risk:** near zero.
- **The problem:** in this system the only available confirmation source is dataset ground truth. Using it turns memory into an oracle and inflates Arm B's results — precisely the contamination [`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §5 warns about. **This policy is not usable as a headline configuration.** It is defensible only as a clearly labelled upper-bound experiment ("what if analyst confirmation were perfect and free"), reported separately and never compared head-to-head against Arm A as the main result. It also cannot be implemented at all until [OQ-2](./07-open-questions.md#oq-2--does-ground-truth-feed-the-memory-store) is decided — [`CLAUDE.md`](../../CLAUDE.md) forbids implementing either interpretation of the §5 question without confirmation.

### Policy comparison

| Policy | Error propagation | Cold-start fill | Bias | Ground-truth contamination |
|---|---|---|---|---|
| `write_all` | High — and measurable | Fastest | None | None |
| `confidence_gated` | Reduced, not removed | Slower | Toward easy cases | None |
| `confirmed_only` | Near zero | Slowest | Toward labelled cases | **Yes — disqualifying for the headline result** |

Whichever is chosen, the policy name and its parameters go in the run manifest and are reported alongside every result. A metric quoted without its write policy is uninterpretable.

**Do not select a policy after seeing which one makes Arm B win.** [`CLAUDE.md`](../../CLAUDE.md) forbids tuning parameters to improve Arm B's results, and the Phase 4 metric definitions are a protected component that may not be adjusted after results are in.

---

## Error propagation

[`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §8 calls this "the single most important failure mode" and requires it be **tested, not just mentioned**.

### The mechanism

```
alert #97 mis-triaged (false_positive, but actually an attack)
  → stored as precedent
  → alert #206 is similar → retrieves #97
  → LLM anchors on the stored verdict → repeats the error
  → #206 stored, reinforcing the pattern
  → the region of embedding space around this attack is now systematically poisoned
```

The failure compounds. Each repetition adds another retrievable instance of the same wrong conclusion, so later alerts retrieve *multiple* consistent-looking precedents for a wrong verdict — which is more persuasive to the LLM than one.

### The test

An **injection experiment**, run as a distinct configuration, not as part of the main comparison.

1. Run Arm B normally. Record the verdict on every alert.
2. Identify a case the system got *right* with high confidence, in a dense region of the space (many near neighbours downstream).
3. Re-run the identical sequence with that one case's stored verdict inverted at write time — everything else unchanged, same alert order, same seeds. The alert stream order and seeds are a protected component and must not be altered to construct this test.
4. Measure, on the alerts *after* the injection point:
   - **Contamination rate** — fraction of downstream alerts that retrieved the poisoned case.
   - **Flip rate** — fraction of contaminated alerts whose verdict changed versus the clean run.
   - **Amplification** — did the poisoned verdict propagate to cases that *didn't* directly retrieve the injected case, via second-generation poisoned writes?
   - **Decay** — does the effect fade as legitimate cases accumulate, or persist to the end of the stream?

Use `precedent_used` ([02](./02-case-schema.md#triage-output-layer-4)) to build the propagation graph: nodes are cases, edges are "this case's verdict cited that case as precedent." Contamination is then reachability from the injected node.

The injected run writes to its **own run directory**. It does not modify the clean run's store ([01 §Store lifecycle](./01-architecture.md#store-lifecycle-and-reproducibility)).

Repeat across several injection points (different attack families, different stream positions, dense vs. sparse regions). A single injection is an anecdote.

**Report the result whatever it shows.** If the LLM turns out to be robust to poisoned precedent, that is a genuine and useful finding.

---

## Idempotency and duplicates

- **Writes are idempotent by `case_id`.** Re-writing the same ID must not create a second vector. Check before writing; a duplicated case double-counts in retrieval and silently up-weights whatever it says. Note that an upsert which *replaces* an existing case is a mutation of stored memory — under the append-only rule in [01](./01-architecture.md#what-this-layer-does-not-do), a same-ID rewrite with different content is an error, not a silent overwrite.
- **Near-duplicate flows are not deduplicated.** Depending on how the alert stream is constructed, bursty attack traffic can produce large numbers of near-identical flow records. Under `write_all`, memory fills with them.
  - **Consequence:** top-k saturates with copies of the same alert. Retrieval returns several variants of one thing instead of several distinct precedents, and effective *k* collapses toward 1.
  - **Severity depends on Layer 1's stream construction**, which is out of scope here — so the memory layer must measure it rather than assume the stream is de-duplicated.
  - Mitigation belongs in the read path (diversity constraints), not the write path — deduplicating on write would discard the volume information that makes a flood look like a flood. See [04 §Near-duplicate saturation](./04-read-path.md#near-duplicate-saturation).
  - Whatever is chosen, measure it: report the mean pairwise similarity among retrieved sets and the count of distinct flows per retrieval.

---

## Failure handling

| Failure | Behaviour |
|---|---|
| Embedding raises | Log, skip the write, continue the run. The verdict is already scored. Never abort the stream. |
| Chroma `add` raises | Same. Record in the write log with the exception. |
| Metadata contains a `None` or a list | **Fail loudly at render time**, not at write time. This is a schema bug, and silently coercing it produces cases that behave differently under `where` filters. |
| `schema_version` mismatch with the collection | Refuse the write and abort the run. A mixed-version store is silently corrupt ([02 §Schema versioning](./02-case-schema.md#schema-versioning)). |

Every skipped write is counted, and the count appears in the run manifest. A run that silently failed to write half its cases must not be reportable as a clean Arm B run.

---

## What the write path must log

[`CLAUDE.md`](../../CLAUDE.md) requires logging enough per decision to reconstruct it later. Per alert, appended to `writes.jsonl`:

```json
{"seq": 412, "case_id": "r7f3a1:000412", "written": true,
 "policy": "write_all", "reason": "write_all",
 "embed_ms": 8.4, "add_ms": 2.1, "collection_count_after": 388}
```

`collection_count_after` gives the exact size of memory at every point in the stream — needed to separate cold-start from steady-state performance in Phase 4 ([`PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md) §7 Phase 3), and impossible to reconstruct afterwards.
