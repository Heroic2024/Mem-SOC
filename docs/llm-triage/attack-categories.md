# LLM Options for MemSOC — Layer 4 (Triage + Reporting)

This document evaluates candidate LLMs for **Layer 4** of the MemSOC architecture (see
`Project Brief — Agentic SOC Capstone Project`, §4). Layer 4 consumes the alert (plus, in
Arm B, retrieved precedent from the memory layer) and produces:

1. A structured verdict (classification, confidence, rationale) — used by the evaluation
   harness and written back into memory.
2. A dual-audience explainable report (technical + non-technical view).

Two categories of LLM were considered: **paid, cost-efficient API models**, and
**free-to-use models** (rate-limited hosted free tiers, and fully free self-hosted
open-weight models). This document exists so the model choice is documented and
reproducible, in the same spirit as the ground-truth-handling decision in §5 of the
project brief — it should be an explicit, recorded decision, not a silent default.

> **Note on pricing:** LLM API pricing changes frequently. Figures below reflect pricing
> as of **August 2026** and should be re-verified against each provider's official pricing
> page before final model selection, especially if there's a gap between writing this
> document and running Phase 4.

---

## Why the model choice matters for this project specifically

MemSOC's core measurement is the *difference* between Arm A (memoryless) and Arm B
(memory-augmented) verdicts. Two properties of the LLM matter more than raw benchmark
quality:

- **Structured output reliability.** The verdict object is parsed programmatically by the
  evaluation harness and written into ChromaDB. A model that occasionally breaks JSON
  format introduces noise unrelated to the memory-layer effect being measured.
- **Not "too smart."** An extremely capable model may partially compensate for missing
  memory through general reasoning strength alone, which would shrink the very effect
  size the experiment is trying to detect. A more literal, mid-capability model makes the
  contrast between arms sharper and more attributable to memory specifically.

Both categories below are evaluated against these two properties, not just cost.

---

## Category 1 — Paid, Cost-Efficient API Models

These are hosted commercial APIs. No local compute required; billed per token.

### Claude Haiku 4.5 — *primary recommendation for the triage call*

| | |
|---|---|
| **Cost** | $1 / $5 per MTok (input/output) |
| **Context window** | 200K tokens |
| **Reproducibility** | Pinned model ID available — won't silently change underneath you |

**Advantages**
- Strong, consistent structured-output / JSON format adherence across high call volumes —
  important since the evaluation harness parses every verdict programmatically.
- Cheapest of the frontier-provider options, which matters at CICIDS2017 scale (thousands
  of calls across both arms).
- Qualifies for further discounts specific to this project's design (see "Cost levers"
  below).
- Deliberately not the most "reasoning-heavy" model — helps keep the memory-layer effect
  measurable rather than masked by raw model capability.

**Drawbacks**
- Less nuanced free-text generation than Sonnet — the report-writing call may read more
  flatly.
- 200K context is smaller than newer models, though still far larger than a single
  alert + top-k retrieved cases will ever need.

**Why use it here specifically**
Best fit for the **triage call** (verdict generation), which runs the most times in the
experiment and needs reliability over nuance.

---

### Claude Sonnet 5 — *optional upgrade for the report-writing call only*

| | |
|---|---|
| **Cost** | $2 / $10 per MTok (introductory, through Aug 31, 2026); $3 / $15 standard from Sep 1, 2026 |
| **Context window** | 1M tokens |

**Advantages**
- Noticeably better at connecting retrieved precedent to a coherent explanation — useful
  for the non-technical audience report.
- Still affordable at this project's scale (2-3x Haiku, not 10x).

**Drawbacks**
- More expensive than Haiku across a full replay if used for *every* call, not just
  report-writing.
- Using a different model for the report call than the triage call is a deliberate
  asymmetry — must be documented explicitly (same principle as the ground-truth decision
  in the project brief) since it means "same LLM used by both arms" applies to the triage
  model, not necessarily the report writer.

**Why use it here specifically**
Only worth the extra cost for the report-generation call, where output quality is
user-facing and not part of the scored comparison between arms.

---

### Gemini 2.5 / 3.5 Flash — *reference alternative*

| | |
|---|---|
| **Cost** | ~$0.15–0.30 / ~$0.60–1.25 per MTok |
| **Context window** | 1M tokens |

**Advantages**
- Cheapest paid closed-model option evaluated.
- Large context window at low cost.

**Drawbacks**
- Slightly less consistent structured-output discipline than Claude models without
  explicit JSON-mode enforcement.
- Adds a second provider/SDK to manage if the rest of the stack is Claude-based.

**Why use it here specifically**
Only if API cost is a hard constraint that Haiku 4.5 doesn't sufficiently solve.

---

### Cost levers that apply regardless of which paid model is chosen

- **Batch API (50% off input + output).** MemSOC's architecture is explicitly an
  *offline alert-replay framework* (§7, Phase 4) — nothing needs a real-time response.
  The entire evaluation run qualifies for batch pricing.
- **Prompt caching (up to 90% off repeated input).** The prompt template is fixed by
  design (§9 — "same prompt template object" across arms). Caching the system prompt and
  schema instructions once, and paying full price only for the per-call alert + retrieved
  context, meaningfully cuts cost.
- **Temperature = 0.** Not a cost lever, but a required setting alongside model choice —
  the alert replay must be deterministic (§4, Layer 1), and the LLM layer should be as
  close to deterministic as possible to avoid introducing noise into the Arm A vs. Arm B
  comparison.

---

## Category 2 — Free-to-Use Models

Two distinct sub-categories: rate-limited hosted free tiers, and fully free self-hosted
open-weight models.

### Groq (free tier) — *good for prototyping, not the full run*

| | |
|---|---|
| **Cost** | $0, no credit card required |
| **Rate limits** | ~30 requests/min, ~1,000 requests/day, ~6-15K tokens/min (varies by model) |
| **Models available** | Llama 3.x, Qwen3, Gemma, Mixtral (open-weight, hosted on Groq's LPU hardware) |

**Advantages**
- Genuinely free, extremely fast inference (LPU hardware).
- Serves the same open-weight model families you could otherwise self-host, so behavior
  transfers reasonably well when moving to local hosting later.
- No cost risk during iterative development.

**Drawbacks**
- Daily request cap will be exhausted quickly during a full CICIDS2017 replay across two
  arms with two LLM calls per alert.
- Hitting the cap mid-run would force a mid-experiment provider switch — a confound the
  project brief explicitly warns against (§3, §9).
- Free tier prompts may be used for provider-side training — avoid for any sensitive data
  (not a major concern with CICIDS2017, which is public, but worth noting as policy).

**Why use it here specifically**
Recommended for **Phase 0–2** (pipeline construction and debugging on a small sample),
where the daily cap is a non-issue and iteration speed matters more than eliminating rate
limits.

---

### Google AI Studio free tier — *comparable alternative to Groq*

| | |
|---|---|
| **Cost** | $0, no credit card required |
| **Rate limits** | ~1,500 requests/day on Gemini 2.5 Flash |
| **Models available** | Gemini 2.5 Flash / Flash-Lite |

**Advantages**
- Best free access to a genuinely capable closed model, not just open-weight models.
- Slightly higher daily cap than Groq.

**Drawbacks**
- Same fundamental problem as Groq at full evaluation scale — the daily cap will be hit
  well before a full replay completes.
- Same mid-run provider-switch risk if the cap is hit.

**Why use it here specifically**
Interchangeable with Groq for early-phase prototyping; pick whichever has more headroom
left on a given day.

---

### Self-hosted, local (Ollama) — *recommended for the full-scale Phase 4 evaluation*

| | |
|---|---|
| **Cost** | $0 ongoing — only your own compute (electricity/time) |
| **Rate limits** | None — bounded only by local hardware speed |
| **Models available** | Llama 3.1 8B Instruct, Qwen3 8B/14B, Gemma 3, Phi-4, and others |
| **Hardware fit** | Matches the project's own listed minimum spec (16GB RAM, GPU optional, 8GB+ VRAM recommended for faster inference) |

**Advantages**
- No rate-limit ceiling at all — the full alert replay can run start-to-finish without
  interruption, which matters directly for reproducibility (§4, Layer 1).
- No mid-experiment provider switching risk — same weights for the entire project
  timeline, addressing the "frozen detector" and "no incidental implementation
  differences" principles in §3 and §9 of the project brief.
- Still satisfies the "LLM: API-based usage" software requirement — Ollama exposes an
  OpenAI-compatible REST API locally, so application code calls it exactly like a cloud
  API, just pointed at `localhost` instead of a remote host.
- Zero marginal cost regardless of dataset size or number of replay runs — useful for the
  tuning sweeps in Phase 3 (top-k, similarity threshold) which require many repeated runs.

**Drawbacks**
- Slower per-call latency without a dedicated GPU.
- Generally less nuanced than a frontier closed model, particularly for the report-writing
  call — a legitimate, documentable limitation rather than something to hide (framed as:
  "optimized for zero marginal cost and full reproducibility over maximum report
  fluency").
- Requires local setup and maintenance (model downloads, occasional version pinning).

**Why use it here specifically**
Recommended for the actual **Phase 4 evaluation** — the run that produces the results
reported in the paper. Removes rate limits and cost as variables entirely, and keeps the
model weights fixed and known for the whole project.

---

## Summary Recommendation

| Phase | Recommended model | Why |
|---|---|---|
| Phase 0–2 (build & debug) | Groq free tier (Llama 3.x or Qwen3) | Fast iteration, zero cost risk, daily cap is a non-issue at prototype scale |
| Phase 3 (tuning sweeps) | Self-hosted Ollama (Llama 3.1 8B or Qwen3 8B) | Many repeated runs needed; zero marginal cost, no rate limit |
| Phase 4 (final evaluation, triage call) | Self-hosted Ollama, **or** Claude Haiku 4.5 if budget allows | Determinism and reproducibility (local) vs. best structured-output reliability at low cost (Haiku) |
| Phase 4 (report-writing call only) | Claude Sonnet 5, if using the paid path | Only the report call benefits meaningfully from the extra nuance; must be documented as an explicit asymmetry |

**Bottom line:** if the project has zero budget, self-hosting via Ollama for the full
evaluation is both free and arguably the *more defensible* choice for a controlled
experiment, since it removes rate limits and provider-side model drift as confounding
variables. If a small budget is available, Claude Haiku 4.5 offers the best combination of
cost and structured-output reliability among paid options, with Batch API and prompt
caching further reducing cost given this project's offline, fixed-prompt design.

Whichever path is chosen, the decision should be recorded explicitly in the experiment
protocol doc (per project brief §11), including the exact model ID/version pinned, since
model choice is a controlled variable in the Arm A vs. Arm B comparison.
