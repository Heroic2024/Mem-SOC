# LLMTriage — Stage 4 Aggregate Security Report

> Standalone, memory-free. This is the report-generation half of
> `PROJECT_BRIEF.md` §4 Layer 4. It does **not** implement the memory
> layer (`docs/memory-layer/`), does not score against
> `ground_truth.csv`, and does not modify anything under
> `final_ml_model_v1/` or `log_generation/`.

## Two-step design

Stage 4 is split into two independent scripts that only communicate
through one file:

| Script | Job | Talks to |
|---|---|---|
| `live_capture.py` | Runs the existing, unmodified detection model over the log stream and **appends** its full output to `model_outputs/live_results.jsonl`, one line per flow, as each result comes back | The existing `/api/logs` endpoint. Nothing else. |
| `generate_report.py` | Reads whatever is currently in `model_outputs/live_results.jsonl`, computes statistics, and generates the report | Only that file, plus the Groq LLM for narrative. **Never** the detection API, **never** `generated_logs.jsonl`. |

This means a report is always built from **the latest outputs the model
has actually produced** — you can run `generate_report.py` while
`live_capture.py` is still capturing, or after it's finished, and either
way it snapshots whatever has accumulated at that moment.

```
[Terminal 1 -- keep running]              [Terminal 2 -- run any time]
live_capture.py                            generate_report.py
   │                                            │
   ▼                                            ▼
POST /api/logs (existing, unmodified)      reads live_results.jsonl
   │                                       (whatever exists right now)
   ▼                                            │
model_outputs/live_results.jsonl ─────────────►│
(grows by one line per flow)                    ▼
                                            statistics + LLM narrative
                                                 │
                                                 ▼
                                     reports/security_report_<ts>.json / .md
                                                 │
                                                 ▼
                                     [Terminal 3] report_server.py
                                     (read-only HTTP API over reports/)
                                                 │
                                                 ▼
                                     [Terminal 4] dashboard/ (React)
                                     fetches and renders it in the browser
```

## Presentation layer (React dashboard)

A third piece, `report_server.py` + `dashboard/`, presents the reports
visually. It is entirely a *consumer* of the two files above — it adds
no processing of its own:

| Component | Role |
|---|---|
| `report_server.py` | A minimal, read-only FastAPI server. Lists and serves the JSON files already sitting in `reports/` over HTTP (a browser can't read the filesystem directly). No statistics, no LLM calls, no detection logic — it never imports `stats_engine.py`, `report_prompt.py`, or `llm_client.py`. |
| `dashboard/` | A React (Vite + JavaScript) single-page app. Fetches from `report_server.py` and renders charts, tables, and the LLM narrative. Contains no report-generation or statistics logic of its own. |

See "Presentation layer architecture" and "Running the dashboard" below
for the full data flow and startup commands, and `dashboard/README.md`
for the frontend's own file layout.

## Setup

```powershell
pip install requests   # already used elsewhere in this repo; skip if present
$env:GROQ_API_KEY = "your-key-here"
```

Get a free key at https://console.groq.com.

**Model note:** `llama-3.1-8b-instant` and `llama-3.3-70b-versatile` were
both deprecated for free/developer-tier Groq accounts on 2026-08-16.
`config.py` uses `openai/gpt-oss-20b`, Groq's documented replacement. If
Groq deprecates this one too in the future, only `GROQ_MODEL` in
`config.py` needs to change.

## Files

| File | Role |
|---|---|
| `config.py` | API key, model id, endpoints, the shared `live_results.jsonl` path, report-sizing constants |
| `live_capture.py` | **The only file that calls the detection API.** Runs the stream through it, appends full results to `model_outputs/live_results.jsonl` |
| `stats_engine.py` | **No network calls at all.** Reads `live_results.jsonl` and computes every statistic in the report |
| `report_prompt.py` | Builds the prompt from verified statistics + a findings sample; parses the LLM's narrative-only JSON response |
| `llm_client.py` | Calls Groq's chat-completions endpoint via `requests` |
| `generate_report.py` | Reads `live_results.jsonl`, orchestrates statistics + LLM, renders the final report |
| `model_outputs/live_results.jsonl` | The hand-off file — one JSON line per flow, append-only. Also read independently by `memory/case_ranker/` (memory-layer case ranking/compaction — see that folder's README). Nothing here changed for that; it's just a second reader of the same file. |
| `reports/` | Output — one `security_report_<timestamp>.json` + `.md` per report generated |
| `report_server.py` | Read-only HTTP API exposing `reports/*.json` for the React dashboard to fetch |
| `dashboard/` | React (Vite + JavaScript) presentation layer — fetches from `report_server.py`, renders it |

## Usage

Start the detection API first (see `log_generation/README.md` for the
cwd/PYTHONPATH note). Then, in a separate terminal:

```powershell
cd Mem-SOC\LLMTriage

# Terminal A -- capture model outputs (pick one):
python live_capture.py                    # one pass through the stream, then stop
python live_capture.py --loop             # never stops, wraps and keeps going
python live_capture.py --loop --interval 1   # paced like a live sensor, 1 flow/sec
python live_capture.py --reset            # start live_results.jsonl empty first
```

```powershell
# Terminal B -- generate a report from whatever has been captured so far,
# any time, whether Terminal A is still running or not:
cd Mem-SOC\LLMTriage
$env:GROQ_API_KEY = "your-key-here"

python generate_report.py                 # everything captured so far
python generate_report.py --limit 500     # only the 500 most recently captured flows
```

`generate_report.py` never starts or drives the capture itself — if
`model_outputs/live_results.jsonl` doesn't exist yet, it tells you to
run `live_capture.py` first rather than doing it for you.

## Report sections

`security_report_<timestamp>.md` contains, in order: Executive Summary,
Security Overview (verified traffic-summary table), Statistics (category
breakdown, confidence distribution, protocol distribution, top targeted
ports, top SHAP indicators — all tables, all computed),
Risk Analysis, Detailed Findings (ranked table), Threat / Attack
Analysis, Recommendations, Prioritized Action Plan, Conclusion, and a
Methodology note.

## Risk scoring methodology

`risk_score = detector_confidence × severity_weight[attack_category]`,
with fixed weights in `stats_engine.SEVERITY_WEIGHTS` (Worms/Backdoor
1.00, Shellcode 0.95, Exploits 0.90, DoS 0.80, Fuzzers 0.55,
Reconnaissance/Analysis 0.50, Generic 0.40 — standard NIDS severity
convention, not a measured value). This is a documented heuristic used
for ranking and prioritization, not a claim about ground-truth severity.

## Model output vs. raw log fields

Every statistic and finding field is sourced from the model's own
response (`status`, `binary_confidence`, `multiclass`, `alert` --
including `alert.dst_port`, `alert.protocol`, `alert.shap_explanation`),
never from the raw log line fed into the model. Two things worth
knowing:

- `uid` is kept in findings purely as a traceability reference (so a
  finding can be pointed back to a specific captured line) -- it is not
  presented as an attack-pattern statistic and is never given to the LLM
  as something to interpret.
- There is **no source-IP statistic**. The model's alert deliberately
  never includes an IP address at all (`memory/SCHEMA_DESIGN.md` B9 --
  source IP predicts the attack label with 100% accuracy on this
  dataset, so exposing it would let a report look insightful for a
  reason that has nothing to do with the model's actual detection).
  Since the model itself never outputs an IP, no IP-based finding can
  legitimately be called a model output, so none is included.

## The statistics-vs-narrative boundary

This is structural, not a prompting convention: `stats_engine.py` never
imports `llm_client.py`, and `generate_report.py`'s Markdown renderer
pulls every table directly from `stats_engine`'s output dicts. The LLM's
JSON response only fills seven free-text fields (`executive_summary`,
`security_overview`, `risk_analysis`, `threat_analysis`,
`recommendations`, `prioritized_action_plan`, `conclusion`) — there is
no code path by which an LLM-invented number reaches a report table.

## Presentation layer architecture

```
reports/*.json  (already written by generate_report.py, unchanged)
        │
        │  read-only file access
        ▼
report_server.py  (FastAPI, port 8001)
        │  GET /api/reports        -> lightweight summary list, newest first
        │  GET /api/reports/{name} -> one full report, verbatim
        │  CORS enabled for local dev
        ▼
dashboard/  (React + Vite, port 5173)
        │  src/api.js        -> fetch() wrappers, the only network code
        │  src/App.jsx       -> report list + selection state, tab layout
        │  src/sections/*    -> one component per tab (Overview, Technical
        │                       Findings, Recommendations, Trends)
        │  src/components/*  -> charts (Recharts), tables, badges, KPI cards
        ▼
   rendered in the browser
```

Nothing under `dashboard/` or in `report_server.py` computes a
statistic, calls the LLM, or touches the detection API — they only ever
display `verified_statistics`, `detailed_findings`, and `llm_analysis`
exactly as `generate_report.py` wrote them.

## Running the dashboard

Three processes, in addition to the detection API:

```powershell
# Terminal 3 -- the report API (after at least one report exists in reports/)
cd Mem-SOC\LLMTriage
python -m uvicorn report_server:app --port 8001
```

```powershell
# Terminal 4 -- the React dev server (one-time: cd dashboard && npm install)
cd Mem-SOC\LLMTriage\dashboard
npm run dev
```

Open the URL Vite prints (default `http://localhost:5173`). The sidebar
lists every retained report; picking one fetches and renders it. The
Trends tab uses the full report list, so it appears once at least 2
reports exist.

## Note on `.gitignore`

`LLMTriage/model_outputs/`, `LLMTriage/reports/`, and
`LLMTriage/dashboard/node_modules/` are generated output/dependencies
and are not explicitly covered by `.gitignore` under those specific
paths (the repo root `.gitignore` does already ignore `node_modules/`
and `*.log`/`*.csv`/etc. globally, so `dashboard/node_modules/` is
already excluded as a side effect — `model_outputs/` and `reports/` are
not). Per `CLAUDE.md`, `.gitignore` is not touched as a side effect of a
feature task — flagging this the same way `data/` was flagged in
`memory/SETUP_PLAN.md`. Say the word if you want it added.
