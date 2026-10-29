# MemSOC Demo Dashboard

The final-presentation dashboard for the MemSOC capstone. Left-rail navigation across eight sections,
each pulling from the project's real, already-computed results or making a genuine live call — nothing
on this dashboard is placeholder or fabricated data.

This is a local-only app. It is never deployed or made public, so the real API keys it uses can live in
a plain `.env` file without being exposed to anyone else.

## What each section demonstrates

**1. Overview** — the four headline numbers (Gemma's missed-attack drop, its recall gain, the 97.6%
copy rate, the family-accuracy cost) as KPI tiles, plus a one-paragraph map of what the rest of the
dashboard covers. This is the 10-second version of the whole project.

**2. Correctly Caught** — real alerts where *both* models' self-memory arm correctly escalated a
genuine attack (`verdict == true_positive`), filtered from the scored result files, not hand-picked.
Demonstrates the recall success concretely, alert by alert, rather than as an abstract percentage. Each
card is honest about a real distinction: catching an attack (the verdict) and naming its family
correctly are different things, and this project's own finding is that the first improved while the
second often didn't — so every card marks whether the family name was *also* verified correct against
ground truth, rather than implying every green card is a clean sweep.

**3. Per-Model Results** — full metrics per model, every arm (A / B-self / B-oracle): recall and
family-accuracy bars, a family-breakdown donut of what B-self's correct catches actually named, a
confidence histogram showing the model is consistently confident (0.85+) when it's right, and a latency
comparison. Demonstrates that memory's effect on Gemma isn't just "more correct" — it's also faster per
alert, a second, independent measurable benefit.

**4. Cross-Model** — Gemma and gpt-oss-20b, scored live from their real per-verdict logs, plus Qwen
3.8 27B included for completeness (static-only — it has no raw log in this repo, so its numbers are
sourced directly from `docs/status/qwen-results.md` rather than recomputed). Demonstrates the project's
actual, defended finding: the effect of memory depends on the model, shown directly rather than averaged
into a single misleading number.

**5. The Mechanism** — the copy rate, the Arm A counterfactual (what the same match rate would be
without memory), and the oracle-memory recovery. Demonstrates *why* memory helped Gemma's recall and
hurt its family-naming in the same run: the model follows retrieved precedents, and oracle memory
(identical retrieval, correct stored labels) isolates that the cause is what was stored, not a retrieval
failure. This causal explanation, not just the headline number, is the project's central contribution.

**6. Statistical Rigor** — per-alert McNemar tests next to a cluster-bootstrap check that resamples
whole near-duplicate groups instead of individual alerts. Demonstrates that the positive result holds up
under a deliberately harder test (Gemma's recall gain survives it), and reports just as directly where a
result does *not* survive it (gpt-oss-20b's apparent significance disappears under the cluster check).
Showing a finding that *doesn't* hold up is itself evidence the ones that do were checked honestly, not
cherry-picked.

**7. Architecture** — the four-layer pipeline and three-experimental-arms diagrams. Demonstrates that
the result comes from a real, designed system with the memory layer as an isolated variable, not an ad
hoc script.

**8. Live Demo** — pick a model and a hand-picked alert, and the dashboard makes a genuine, real-time
call to the actual evaluated model (Gemma via Google AI Studio, gpt-oss-20b via GroqCloud), walking
through every real step: the alert, the case text built for embedding, the real vector search against
the actual ChromaDB memory store, the retrieved precedents with their similarity scores, the literal
text block injected into the prompt, the live verdict, and a live check of whether the memory arm just
copied its precedents — plus a "does this match the recorded result?" reproducibility badge. Demonstrates
the whole pipeline is real and working right now, not a recording. Below the main demo, the **Confirmed
Catches Browser** lists every real correct catch from both models with a "replay" button that reruns
that exact alert live, so a true-positive claim can be checked on the spot rather than taken on faith.

## How this adds up to showing the project succeeded

The project's claim was never "memory always helps" — it was "does persistent memory measurably change
LLM triage, and if so, how and why." Success here means that question got a real, defensible answer, not
that every number came back positive. Concretely, this dashboard demonstrates:

- **A real, statistically significant improvement**, on the strongest model, that survives a
  deliberately adversarial statistical check (the cluster bootstrap) rather than only a favorable one.
- **A causal mechanism, not just a correlation** — the oracle-memory comparison pins the cause down to
  what gets stored, which is a stronger result than "the number went up."
- **A second independent benefit** (latency) that moves the same direction as recall, which would be a
  strange coincidence if the recall gain weren't real.
- **A live, reproducible system** — the Dynamic section isn't a recording; every claim it makes can be
  re-run on the spot against the real models and the real memory store.
- **Honesty under its own scrutiny** — the dashboard shows exactly where the effect does and doesn't
  hold (gpt-oss-20b's regression, the family-accuracy cost, Qwen's floor effect) rather than hiding the
  parts that complicate the story, which is what makes the positive parts credible in the first place.

## Why this is trustworthy, not a mockup

Every step in the Dynamic section calls the project's own, already-
tested code — `memsoc.memory.store.MemoryLayer`, `memsoc.triage.
triage_prompt`, `memsoc.triage.llm_client` — rather than reimplementing
any of it. The Dynamic section reads from an **isolated copy** of the
real memory stores (`backend/demo_artifacts/`), so nothing it does can
ever modify the original archived evaluation results. If a live call
fails for any reason (network, rate limit, malformed response), the
dashboard automatically falls back to that alert's real, originally
recorded result and shows a visible "live call failed — showing
recorded result" badge — it never silently breaks mid-demo.

## Prerequisites

- Node.js (for the frontend)
- A Python environment with `chromadb==1.5.9` and
  `sentence-transformers==6.1.0` already installed — the project's own
  `memsoc-memory-protocol` virtual environment already has both; reuse
  it rather than installing fresh.
- Two API keys, in a `.env` file at the **repo root** (`Mem-SOC/.env`,
  not inside `demo-dashboard/`):

  ```
  GEMINI_API_KEY=...
  GROQ_API_KEY=...
  ```

  `GEMINI_API_KEY` comes from [Google AI Studio](https://aistudio.google.com)
  ("Get API key"); `GROQ_API_KEY` from your GroqCloud account. Both are
  free-tier eligible — the same tier the project's original evaluation
  runs used.

## One-time setup

```powershell
# Backend
cd demo-dashboard/backend
<path to memsoc-memory-protocol venv>\Scripts\pip install -r requirements.txt
<path to memsoc-memory-protocol venv>\Scripts\python static_export.py   # builds the Static sections' data

# Frontend
cd ../frontend
npm install
```

`static_export.py` re-aggregates `artifacts/runs/*/triage_verdicts.jsonl`
through the project's own `score_verdicts.py` — nothing here calls an
LLM or runs a new experiment. It writes `model_gemma.json`,
`model_gptoss.json`, `cross_model.json` (including Qwen's published
numbers) and `true_positive_showcase.json` (the real overlap of both
models' correct catches, with ground-truth family-correctness flags).
Re-run it any time the underlying run data changes; everything
downstream of it is just rendering.

## Running it

Two terminals, both left open for the duration of the demo:

```powershell
# Terminal 1 — backend
cd demo-dashboard/backend
<path to memsoc-memory-protocol venv>\Scripts\python -m uvicorn main:app --port 8090

# Terminal 2 — frontend
cd demo-dashboard/frontend
npm run dev
```

Open **http://localhost:5173**. Nothing is published or publicly
reachable — both servers only listen on localhost.

The backend warms up both models' memory stores at startup (loading
the embedding model once takes a few seconds), so the very first live
click during the actual presentation isn't slowed down by a cold start.

## Using the Dynamic section live

Gemma can take 20–40 seconds per call (it's a reasoning model and
spends tokens thinking before answering — the dashboard shows an
elapsed-time indicator so this doesn't read as broken); gpt-oss-20b
typically answers in 2–3 seconds. Arm A and the memory arm are called
**concurrently**, so the wait is one call's latency, not two. Pace a
live demo accordingly — gpt-oss-20b is the better choice for a quick
back-and-forth, Gemma for a single deliberate "watch it think" moment.

Only a curated shortlist of alerts is exposed (not all 165) — four per
model, each picked to tell one clear, specific story (the report's own
worked example, a repeated case of the same harm, a case where memory
fixed an Arm A miss, a repeated case of the same help). Every button in
the picker shows a color-coded outcome tag (amber "harm", green "help")
so what it demonstrates is visible before clicking, not just in the
note underneath. The shortlist lives in `backend/demo_alerts.py` as
`{uid, seq, label, outcome, note}` entries and can be extended — any
`uid` that exists in both `artifacts/model_outputs/live_results.jsonl`
and `artifacts/generated_logs.jsonl` will work.

## Project layout

```
demo-dashboard/
├── backend/
│   ├── main.py              FastAPI app -- /static/*, /live/*, startup warm-up
│   ├── live_demo.py          the live pipeline: retrieve -> inject -> call -> parse
│   ├── static_export.py      builds static_data/*.json from score_verdicts.py
│   ├── demo_alerts.py         the curated alert shortlist (4 per model)
│   ├── demo_artifacts/        isolated copies of the real ChromaDB memory stores
│   │                          (read-only in spirit; never written to by this app)
│   └── static_data/           generated JSON bundles (git-ignorable, rebuildable)
└── frontend/
    ├── public/diagrams/        the four-layer pipeline and three-arms diagram images
    ├── src/
    │   ├── App.jsx             left-rail navigation across all eight sections
    │   ├── api.js               the only network code in the app
    │   ├── components/
    │   │   ├── Donut.jsx          family-breakdown chart
    │   │   └── Histogram.jsx      confidence-distribution chart
    │   ├── sections/
    │   │   ├── Overview.jsx
    │   │   ├── CorrectlyCaught.jsx
    │   │   ├── PerModelResults.jsx
    │   │   ├── CrossModel.jsx
    │   │   ├── Mechanism.jsx
    │   │   ├── StatisticalRigor.jsx
    │   │   ├── Architecture.jsx
    │   │   └── DynamicSection.jsx   live demo + Confirmed Catches Browser
    │   └── index.css              the cream/peach theme
    └── vite.config.js          dev-server proxy to the backend on :8090
```

## Known limitations

- Qwen 3.8 27B is **Static-section only** — it has no raw per-alert log
  or memory store available, so it can't be replayed or called live the
  way Gemma and gpt-oss-20b can, and it's excluded from the Correctly
  Caught and Confirmed Catches Browser components for the same reason.
- This is genuinely live: each click spends real API quota. That's
  trivial next to what the full 165-alert evaluation runs already used,
  but it does mean results can vary slightly between runs (the models
  are not perfectly deterministic even at temperature 0) — the
  reproducibility badge in the Dynamic section reports this honestly
  rather than hiding it.
- Venue network reliability is the one thing this dashboard can't
  control for; the fallback-to-recorded-result behavior exists
  specifically so a bad connection at the venue degrades gracefully
  instead of visibly failing.
