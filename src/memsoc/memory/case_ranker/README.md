# Memory-Layer Case Ranker

Reads the detection model's own captured output, ranks the most
critical/severe attacks by risk, and compresses the highest-ranked
ones into a single compact, metrics-only, ≤256-token digest — the text
meant to be handed to the memory layer's future embedding step
(`docs/memory-layer/`).

This component does **not** call an embedding model, does **not**
touch ChromaDB, and does **not** write to any memory store. Those
remain future work. Its only job is: **rank, select, compress.**

---

## Where this sits

```
LLMTriage/live_capture.py                 (existing, unmodified)
        │  POST /api/logs to the existing detection API
        ▼
LLMTriage/model_outputs/live_results.jsonl   <-- the hand-off file
        │
        │  read by TWO independent consumers:
        │
        ├──► LLMTriage/generate_report.py     (Stage 4 — human-readable report)
        │
        └──► memory/case_ranker/build_memory_input.py   (this component)
                    │
                    ▼
             memory/case_ranker/outputs/memory_input_<ts>.json / .txt
                    │
                    ▼
             (future) embedding model → ChromaDB   [not built yet]
```

**Input is model output, never raw logs.** `live_results.jsonl` holds
the model's real `status`/`binary`/`multiclass`/`alert` response per
flow — this component never reads `log_generation/generated_logs.jsonl`
(the raw input records fed *into* the model).

**Why it lives in `memory/`, not `LLMTriage/`:** this is memory-layer
work — a scoped-down version of the `CaseRenderer` already planned in
`memory/SETUP_PLAN.md` ("the single shared renderer, with the hard
token-limit assertion"). `LLMTriage/` stays exclusively Stage 4
(reporting); nothing in it was modified for this component.

**Why `risk.py` duplicates `LLMTriage/stats_engine.py`'s scoring
instead of importing it:** every top-level component in this repo is
self-contained and talks to the others only through files, never
through cross-folder Python imports (`log_generation`'s eligibility
check is a documented independent re-implementation of the same rule
`final_ml_model_v1` uses — see `log_generation/README.md`). This
follows that same pattern. If `SEVERITY_WEIGHTS` or the risk
thresholds ever change, update both `risk.py` and
`LLMTriage/stats_engine.py` together.

---

## Files

| File | Role |
|---|---|
| `config.py` | Paths, `TOKEN_BUDGET=256`, `SAFETY_MARGIN`, `SHAP_TOP_K` |
| `risk.py` | Severity weights + `risk_score()`/`risk_level()` — mirrors `LLMTriage/stats_engine.py` |
| `token_estimator.py` | Heuristic token counter — no `transformers`/`torch` dependency |
| `build_memory_input.py` | The runnable script |
| `outputs/` | Generated at runtime — one `.json` + `.txt` pair per run |

## Usage

```powershell
cd Mem-SOC\memory\case_ranker
python build_memory_input.py                # rank everything captured so far
python build_memory_input.py --limit 500     # only the 500 most recently captured flows
```

Requires `LLMTriage/model_outputs/live_results.jsonl` to already exist
— run `LLMTriage/live_capture.py` first if it doesn't. This script
never starts capture itself.

---

## How ranking works

Every attack-status record in `live_results.jsonl` is deduplicated by
`uid` first (see "A real bug this caught" below), then scored:

```
risk_score = detector_confidence × severity_weight[attack_category]
```

using the exact same `SEVERITY_WEIGHTS` table as Stage 4's reports
(Worms/Backdoor 1.00, Shellcode 0.95, Exploits 0.90, DoS 0.80,
Fuzzers 0.55, Reconnaissance/Analysis 0.50, Generic 0.40). Sorted
descending — highest `risk_score` first.

## How the 256-token output is built

1. A header line of pure aggregate numbers is built first: total flows
   scanned, distinct attack count, attack rate %, overall risk level,
   and the full severity distribution (`SEV=C48/H35/M91/L20`) —
   computed over **every** ranked attack, not just the ones that end
   up fitting the budget.
2. Ranked cases are added one at a time, highest risk first. Each
   candidate addition is measured with `estimate_tokens()`; the moment
   adding the next case would exceed the effective budget
   (`TOKEN_BUDGET − SAFETY_MARGIN` = 252), the loop stops.
3. A case is either **fully included or fully dropped** — never
   truncated mid-line — so the digest is always syntactically
   complete and never cuts off half a case.

`SAFETY_MARGIN = 4` exists because `estimate_tokens()` is a heuristic
(see below), and a real tokenizer reserves a couple of positions for
special tokens (`[CLS]`/`[SEP]`) — packing to 252 rather than exactly
256 leaves headroom for both.

## How SHAP is used

Each included case carries its top `SHAP_TOP_K` (default 3) features
straight from the model's own `alert.shap_explanation` — the same
per-alert, deterministically-ordered SHAP output `final_ml_model_v1`
already produces, not recomputed here. Rendered as
`shap=[FEATURE:VALUE,...]`, e.g. `shap=[LONGEST_FLOW_PKT:0.8654,
CLIENT_TCP_FLAGS:0.7094,MIN_TTL:0.6394]` — feature name and signed
SHAP value only, no impact-direction prose.

## Why the output has no natural language

Every field is a number or a closed-vocabulary category label
(`cat=Exploits`, `sev=Critical`, `proto=TCP`) — never a sentence. This
is a deliberate departure from the illustrative template sketched in
`docs/memory-layer/02-case-schema.md` (which described embedding
9-line, sentence-like case text) — that document is explicitly marked
"proposal, not settled," and this component implements a different,
more recent, and more explicit requirement: metrics only, no
descriptions or recommendations. If the memory layer's actual case
schema is later locked to the prose-style template instead, this
component's output format would need revisiting — flagged here rather
than silently reconciled.

## Token estimation — heuristic, not exact

`token_estimator.py` approximates WordPiece behavior without installing
`transformers`/`torch` (~1.5–2.5GB, per `memory/SETUP_PLAN.md`) just to
count tokens. This mirrors `memory/SCHEMA_DESIGN.md`'s own B10
token-budget measurement, which used the same kind of heuristic for the
same reason and carried the same caveat: **treat the 256-token cap as a
conservative approximation.** Re-verify with the real tokenizer once
`sentence-transformers` is installed for the actual embedding step.

## A real bug this caught

The first real run against the live capture (6,525 flows, produced by
`live_capture.py --loop`) surfaced literal duplicate entries in the
ranked output — the same `uid` appearing twice with identical data.
Cause: `--loop` wraps and re-replays the stream, so the same flow gets
captured more than once in `live_results.jsonl`. Without
deduplication, a repeated flow occupied two ranked slots and crowded
out a genuinely different case within the token budget — exactly the
"near-duplicate saturation" risk already documented in
`docs/memory-layer/04-read-path.md`. `rank_attacks()` now deduplicates
by `uid` before scoring (first occurrence wins; repeats carry identical
data anyway).

**Not fixed, and out of scope here:** `LLMTriage/stats_engine.py`
does **not** deduplicate `live_results.jsonl` by `uid`, so Stage 4's
`attack_count`/`attack_rate_pct` in the security report can be
similarly inflated by repeated `--loop` captures of the same flow.
Flagging this rather than fixing it, since `stats_engine.py` is the
existing Stage 4 pipeline and changing it wasn't requested here.

## Output format

`memory_input_<timestamp>.json`:

```json
{
  "generated_at": "2026-08-28T15:14:10+00:00",
  "source_file": ".../LLMTriage/model_outputs/live_results.jsonl",
  "flows_considered": 6525,
  "token_budget": 256,
  "safety_margin": 4,
  "estimated_tokens": 237,
  "summary": {
    "total_flows": 6525, "attack_count": 194, "attack_rate_pct": 2.97,
    "overall_risk_level": "Critical",
    "severity_distribution": {"Critical": 48, "High": 35, "Medium": 91, "Low": 20}
  },
  "candidates_ranked": 194,
  "candidates_included": 5,
  "candidates_dropped_for_budget": 189,
  "included_case_ids": ["C1424236690182-60987-4601", "..."],
  "embedding_input_text": "FLOWS=6525 ATTACKS=194 RATE=2.97% RISK=Critical SEV=C48/H35/M91/L20\n#1 id=... cat=Shellcode sev=Critical risk=0.9093 ..."
}
```

`memory_input_<timestamp>.txt` contains only `embedding_input_text` —
the literal string a future embedding step would consume.

## How this feeds the memory layer later

`embedding_input_text` is exactly the kind of compact per-run digest
`docs/memory-layer/01-architecture.md`'s `CaseRenderer` is meant to
produce before `EmbeddingFunction.encode()` runs. Once the embedding
model and ChromaDB store are actually built:

1. `build_memory_input.py`'s output (or a per-case variant of it — see
   the "one output vs one per case" note below) becomes the text
   `EmbeddingFunction.encode()` embeds.
2. The resulting vector, plus `included_case_ids` and `summary` as
   metadata, is what `MemoryStore`/`Writer` would persist.

**Open design note, not resolved here:** this component currently
produces **one combined digest** covering multiple top-ranked cases,
per the literal instruction ("produce *a* 256-token output"). The
memory-layer docs' own case schema (`02-case-schema.md`) describes
embedding **one case per vector** instead. Which of these the actual
embedding step should consume is a decision for whoever builds that
step next — this component's job stops at producing the compact,
budget-respecting text; it does not decide how it gets embedded.
