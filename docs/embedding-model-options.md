# Embedding Model Options

> Feeds [OQ-8](./07-open-questions.md#oq-8--which-embedding-model-is-locked-for-phase-2)
> ("which embedding model is locked for Phase 2") and the Phase 0 measurement
> requirement in [`05-configuration.md`](./05-configuration.md#embedding-model).
> This file does not change either document's status — OQ-8 stays **open**
> until the team approves a lock on the basis of the token-length measurement
> it already specifies. This is the options survey that measurement is meant
> to be judged against.

**Status:** reference material. Not a decision record — record the actual
answer in [`decisions.md`](../decisions.md) C2 and OQ-8 once made.

---

## 1. What the embedding model actually has to do here

The memory layer's read and write paths both turn a rendered case into a
vector, and similarity between those vectors is the entire retrieval
mechanism — there is no second-stage reranker, no keyword fallback. Three
properties of this project make the choice narrower than "pick a strong
model off a leaderboard":

- **The text is short and structured, not prose.** A rendered case is a
  dense line of feature values, a predicted category, and a handful of
  named contributing fields — closer to a database record flattened to
  text than to a sentence a model like this is normally benchmarked on.
- **The token budget is tight and the failure mode is silent.** The case
  template targets roughly 120–160 tokens against MiniLM's 256-token
  limit ([`05-configuration.md`](./05-configuration.md#token-budget)), and
  exceeding a model's limit truncates without error — the vector still
  looks valid, it is just computed from partial text
  ([R5](./06-risks-and-limitations.md#r5--silent-truncation-at-the-token-limit)).
  Sequence-length headroom is therefore a correctness property of the
  model choice, not a performance detail.
- **The model is a protected component once locked.** [`CLAUDE.md`](../../CLAUDE.md)
  forbids changing it after Phase 2 begins without re-rendering every
  stored case. Determinism — same input, same vector, every time, on the
  same machine — matters more here than squeezing out the last point of
  retrieval accuracy.

---

## 2. Evaluation criteria, in priority order for this project

1. **Determinism.** Fixed weights, no hosted inference, no provider-side
   model updates that could silently change what a stored vector means.
2. **Sequence-length headroom** against the rendered case template.
3. **Runs locally on CPU at the scale this project needs** (a few thousand
   cases, not web-scale) without a new heavy dependency chain.
4. **Retrieval quality on short, structured text** — not general
   sentence-similarity benchmark rank, which is tuned for prose.
5. **License** permits the use this project makes of it.

Raw MTEB leaderboard position is deliberately **not** the top criterion.
The strongest general-purpose embedding model is worthless here if it
can't satisfy criterion 1.

---

## 3. Unpaid / local candidates

| Model | Dim | Max tokens | Params | License | Runs locally |
|---|---|---|---|---|---|
| `all-MiniLM-L6-v2` | 384 | 256 | 22M | Apache-2.0 | Yes |
| `all-mpnet-base-v2` | 768 | 384 | 109M | Apache-2.0 | Yes |
| `BAAI/bge-small-en-v1.5` | 384 | 512 | 33M | MIT | Yes |
| `BAAI/bge-base-en-v1.5` | 768 | 512 | 109M | MIT | Yes |
| `intfloat/e5-small-v2` | 384 | 512 | 33M | MIT | Yes |
| `nomic-ai/nomic-embed-text-v1.5` | 768 (truncatable) | 8192 | 137M | Apache-2.0 | Yes |

### `all-MiniLM-L6-v2` — the candidate already named in the brief

**How it solves the objective:** fast enough that embedding thousands of
cases and every live query costs nothing but CPU time; 384-dimensional
output keeps the store small; already measured once in this project's own
sandbox work (`decisions.md` records its match-rate behavior directly).

**Advantages:**
- Already named in `PROJECT_BRIEF.md` §6 — choosing it is not a new
  decision, only a confirmation, which `05-configuration.md` itself notes
  as a reason to stay with it if the measurement supports it.
- Smallest, fastest model in this table. On CPU, the practical choice for
  a project with no GPU budget.
- Already has version-pin evidence in `decisions.md` C2: the sandbox ran
  it under `sentence-transformers 6.1.0` / `torch 2.14.0+cpu`.

**Disadvantages:**
- 256-token limit is the **tightest** of any candidate here — exactly the
  constraint OQ-8 flags as needing to be measured before lock, and the one
  C3 already found the *long* case-description format silently violated
  (179 of 211 cases truncated).
- Lowest retrieval quality ceiling of the sentence-transformers options in
  this list, by design — it trades accuracy for speed.

**Access:**
```bash
pip install sentence-transformers==6.1.0
```
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
vec = model.encode(text, normalize_embeddings=True)
```
Model card: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2

---

### `all-mpnet-base-v2` — the upgrade path if headroom or quality is short

**How it solves the objective:** if the Phase 0 token measurement shows
MiniLM's 256-token limit does not comfortably fit the final case template,
or if retrieval quality on the structured case text turns out to be the
binding constraint rather than the template length, this is the
straightforward next step within the same library and the same access
pattern — no new dependency, just a different checkpoint name.

**Advantages:**
- Longer sequence limit (384 tokens) gives real headroom over the current
  template's 120–160 token target.
- Generally the strongest general-purpose model in the sentence-
  transformers family on their own benchmark suite — a legitimate quality
  upgrade, not just a different trade-off.
- Same library, same API, same determinism properties as MiniLM — swapping
  between them during Phase 0 measurement is a one-line change.

**Disadvantages:**
- About 5x the parameters and measurably slower per embedding than
  MiniLM — noticeable at the live-query path, not just at write time.
- Larger vectors (768 vs. 384 dim) mean a larger on-disk store for the
  same number of cases.

**Access:** identical pattern to MiniLM, substitute the model name:
```python
model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
```
Model card: https://huggingface.co/sentence-transformers/all-mpnet-base-v2

---

### `BAAI/bge-small-en-v1.5` and `BAAI/bge-base-en-v1.5`

**How it solves the objective:** BGE models are trained specifically for
retrieval rather than general sentence similarity, which is a closer match
to what the memory layer actually does (rank stored cases by relevance to
a query alert) than MiniLM's original training objective.

**Advantages:**
- Strong retrieval-specific benchmark performance for their size class —
  the small variant is roughly MiniLM-sized but trained for the task this
  project actually needs.
- 512-token limit, double MiniLM's headroom.
- MIT license.

**Disadvantages:**
- BGE's documented best practice adds an instruction prefix to *queries*
  for retrieval tasks (`"Represent this sentence for searching relevant
  passages: "`), which is not needed for the symmetric case-vs-case
  comparison this project does on the write side — introduces an
  asymmetry to manage correctly between read and write, exactly the class
  of bug [R4](./06-risks-and-limitations.md#r4--embedding-model-mismatch)
  warns about if handled inconsistently.
- Newer, smaller community track record than the sentence-transformers
  canonical models at the time of writing.

**Access:**
```bash
pip install sentence-transformers
```
```python
model = SentenceTransformer("BAAI/bge-small-en-v1.5")
```
Model card: https://huggingface.co/BAAI/bge-small-en-v1.5

---

### `intfloat/e5-small-v2`

**How it solves the objective:** comparable size/speed class to MiniLM,
trained with a retrieval-oriented contrastive objective similar in spirit
to BGE.

**Advantages:** small, fast, 512-token limit, MIT license.

**Disadvantages:** E5 *requires* `"query: "` / `"passage: "` prefixing on
every input as part of its trained behavior, not an optional tweak — doing
it inconsistently between read and write silently degrades the embedding
quality rather than erroring, the same silent-failure shape this project
has already had to guard against once (the 256-token truncation in C3).
That makes it a strictly higher-discipline choice than BGE for the same
class of benefit.

**Access:**
```python
model = SentenceTransformer("intfloat/e5-small-v2")
# vec = model.encode("passage: " + text)   # write path
# qvec = model.encode("query: " + text)    # read path
```
Model card: https://huggingface.co/intfloat/e5-small-v2

---

### `nomic-ai/nomic-embed-text-v1.5`

**How it solves the objective:** if the case template ever needs to grow
well beyond a few hundred tokens — for instance if OQ-9's Layer 2 contract
ends up including longer free-text fields — this is the only candidate
here with headroom to spare (8192 tokens) rather than headroom to measure
carefully.

**Advantages:**
- Sequence length is a non-issue at this project's scale.
- Matryoshka-style embeddings let the output be truncated to smaller
  dimensions (256/128/64) if store size becomes a concern later, without
  re-embedding.
- Apache-2.0 license.

**Disadvantages:**
- Needs `trust_remote_code=True` to load through `sentence-transformers`
  and pulls in `einops` as an extra dependency — exactly the "new
  dependency" `CLAUDE.md` asks to be justified before adding, and arguably
  not justified when the current template is nowhere near 256 tokens, let
  alone 8192.
- Like E5, requires task-prefixed inputs (`"search_document: "` /
  `"search_query: "` / others), another place for read/write asymmetry to
  creep in.
- Meaningful overkill for this project's actual template size right now.

**Access:**
```bash
pip install einops
```
```python
model = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)
```
Model card: https://huggingface.co/nomic-ai/nomic-embed-text-v1.5

---

## 4. Paid / API candidates

Included because it was asked for directly — not because any of these fit
this project's already-established constraints. `05-configuration.md`
lists "no API dependency, no per-call cost, no network variance" as a
**positive property** of the local candidate already named in the brief,
and that same determinism requirement is what rules every option below
out for the actual implementation, not a weakness specific to any one of
them.

| Model | Dim | Price | Runs locally |
|---|---|---|---|
| OpenAI `text-embedding-3-small` | 1536 (truncatable) | $0.02 / 1M tokens | No |
| OpenAI `text-embedding-3-large` | 3072 (truncatable) | $0.13 / 1M tokens | No |
| Cohere `embed-english-v3.0` | 1024 | ~$0.10 / 1M tokens | No |
| Voyage AI `voyage-3-lite` | 512 | ~$0.02 / 1M tokens | No |

### Best paid option: OpenAI `text-embedding-3-small`

**How it would solve the objective:** cheapest of the credible paid
options, strong retrieval benchmark performance, and its embedding
dimension is truncatable (Matryoshka representation), so storage cost can
be tuned down without re-embedding.

**Advantages:**
- No local model to download, version, or run — zero local compute cost.
- Consistently strong general retrieval performance, ahead of every local
  candidate above on most public retrieval benchmarks.
- Simple REST API.

**Disadvantages — why this project's own constraints rule it out:**
- **Breaks determinism.** This project already flagged, in `decisions.md`
  D3, that its *LLM* calls drift over time on a hosted provider —
  "re-running two pilot verdicts through an identical prompt changed one
  answer." A hosted embedding API carries the identical risk: OpenAI does
  not guarantee a given model checkpoint's weights are frozen forever, and
  a provider-side update would silently change what every previously
  stored vector means relative to a newly embedded query.
- **Every retrieval becomes a network call**, at both write time (storing
  a case) and read time (every live query), for a component intended to
  run fast and locally.
- **Violates the project's own "no API key, no `.env` file" committed-
  artifact rule** in spirit — the embedding path would now also need
  credential handling, which the local candidates never require.
- Not actually necessary at this project's scale: the retrieval-quality
  gap over a local option like `bge-small-en-v1.5` is unlikely to be the
  binding constraint when the real bottleneck is case-template design
  ([OQ-9](./07-open-questions.md#oq-9--what-does-layer-2-emit)), not raw
  embedding quality.

**Access (for reference only):**
```bash
pip install openai
```
```python
from openai import OpenAI
client = OpenAI(api_key="...")
resp = client.embeddings.create(model="text-embedding-3-small", input=text)
vec = resp.data[0].embedding
```
Pricing and signup: https://platform.openai.com/docs/guides/embeddings

---

## 5. Recommendation

**Best unpaid, and the recommendation for this project: `all-MiniLM-L6-v2`,
conditional on the Phase 0 token measurement OQ-8 already requires.** It
is the model named in the brief, it is the one already exercised in this
project's own sandbox work, and locking it avoids relitigating a settled-
looking choice for no measured benefit.

**If that measurement shows the final case template does not comfortably
fit 256 tokens,** move to `all-mpnet-base-v2` first — same library, same
access pattern, same determinism properties, just more headroom and a
quality step up. Reach for `bge-small-en-v1.5` only if retrieval quality
on the structured case text, not sequence length, turns out to be the
binding constraint, and only with the query-prefix asymmetry handled
explicitly and tested against [R4](./06-risks-and-limitations.md#r4--embedding-model-mismatch).

**Best paid, if this project's determinism and no-network-dependency
constraints were ever relaxed: OpenAI `text-embedding-3-small`.** It is
not recommended for the current architecture — see §4 for exactly which
of this project's own already-written rules it would conflict with.

**Next step, not a new one:** this file does not replace the measurement
OQ-8 already calls for. Render a representative sample of cases under the
final template, tokenize each against MiniLM's limit, and report the p50
and p99 — the same task `05-configuration.md` and OQ-8 both already
specify. This file exists so that if that measurement comes back
unfavorable, the next choice is already reasoned through instead of being
picked under time pressure.
