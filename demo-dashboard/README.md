# MemSOC Demo Dashboard

The final-presentation dashboard for the MemSOC capstone, in two sections:

- **Static** — the project's findings: per-model results, cross-model
  comparison, the copying mechanism, and the statistical-rigor check
  (Wilson intervals, McNemar, and the cluster-bootstrap check), all
  pulled from numbers the project has already computed and published.
- **Dynamic** — a live demo. Pick a model and a hand-picked alert, and
  the dashboard makes genuine, real-time calls to the actual evaluated
  models (Gemma 4 26B via Google AI Studio, gpt-oss-20b via GroqCloud),
  walking through every step of the real memory pipeline as it happens:
  the alert, the case text built for embedding, the real vector search
  against the actual ChromaDB memory store, the retrieved precedents
  with their similarity scores, the literal text block injected into
  the prompt, the live verdicts from both arms side by side, and a
  live check of whether the memory arm just copied its precedents.

This is a local-only app. It is never deployed or made public, so the
real API keys it uses can live in a plain `.env` file without being
exposed to anyone else.

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
<path to memsoc-memory-protocol venv>\Scripts\python static_export.py   # builds the Static section's data

# Frontend
cd ../frontend
npm install
```

`static_export.py` re-aggregates `artifacts/runs/*/triage_verdicts.jsonl`
through the project's own `score_verdicts.py` — nothing here calls an
LLM or runs a new experiment. Re-run it any time the underlying run
data changes; everything downstream of it is just rendering.

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

Only a curated shortlist of alerts is exposed (not all 165) — each one
was picked because it tells a clear story (the report's own worked
example, a case where memory helped, a case where it copied a wrong
label). The shortlist lives in `backend/demo_alerts.py` and can be
extended by adding more `{uid, seq, label, note}` entries — any `uid`
that exists in both `artifacts/model_outputs/live_results.jsonl` and
`artifacts/generated_logs.jsonl` will work.

## Project layout

```
demo-dashboard/
├── backend/
│   ├── main.py            FastAPI app — /static/*, /live/*, startup warm-up
│   ├── live_demo.py        the live pipeline: retrieve -> inject -> call -> parse
│   ├── static_export.py    builds static_data/*.json from score_verdicts.py
│   ├── demo_alerts.py       the curated alert shortlist
│   ├── demo_artifacts/      isolated copies of the real ChromaDB memory stores
│   │                        (read-only in spirit; never written to by this app)
│   └── static_data/         generated JSON bundles (git-ignorable, rebuildable)
└── frontend/
    ├── src/
    │   ├── App.jsx           top-level Static / Dynamic tab switch
    │   ├── api.js             the only network code in the app
    │   ├── sections/
    │   │   ├── StaticSection.jsx    findings, charts, stats
    │   │   └── DynamicSection.jsx   the live-demo walkthrough
    │   └── index.css
    └── vite.config.js        dev-server proxy to the backend on :8090
```

## Known limitations

- Qwen 3.8 27B is **Static-section only** — it has no raw per-alert log
  or memory store available, so it can't be replayed or called live the
  way Gemma and gpt-oss-20b can.
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
