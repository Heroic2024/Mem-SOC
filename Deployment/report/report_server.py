"""
Stage 4 report API -- minimal, read-only.

This is the ONLY new piece of Python in this task. It exposes the JSON
report files that generate_report.py already writes to reports/, over
HTTP, so a browser-based React app can fetch() them -- a browser cannot
read arbitrary files from the local filesystem directly, so some HTTP
server has to sit in between.

It does NO processing of its own: no statistics, no LLM calls, no
detection. It never imports stats_engine.py, report_prompt.py, or
llm_client.py. It only reads files that already exist on disk and
returns their contents. All computation still happens exactly where it
did before, via generate_report.py.

This is a separate server from final_ml_model_v1/src/api/server.py (the
detection API) -- different concern, different port, not touched.

Usage:
    python -m uvicorn report_server:app --port 8001
"""

import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import config

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

# Only the current report schema's naming convention is served. This
# also excludes reports/sample-fuzzers_report.json, a stale file from
# an earlier, incompatible single-alert report format that predates the
# aggregate-statistics redesign -- it has a different JSON shape
# entirely and was never meant to be read by this API.
REPORT_NAME_PATTERN = re.compile(r"^security_report_\d{8}_\d{6}$")

app = FastAPI(title="MemSOC Stage 4 Report API")

# Local development only: the React dev server runs on a different port
# (Vite default 5173) than this API, so the browser needs CORS allowed
# to fetch across ports. This API is read-only, local-only, and serves
# no secret data -- there is nothing here to protect with a stricter
# origin policy for a capstone project running on localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _list_report_files():
    return sorted(REPORTS_DIR.glob("security_report_*.json"), reverse=True)


@app.get("/health")
def health():
    return {"status": "ok", "reports_dir": str(REPORTS_DIR)}


@app.get("/api/reports")
def list_reports():
    """
    Lightweight summary of every currently retained report, newest
    first -- enough for the dashboard's report picker and trend view
    without transferring every report's full payload up front.
    """

    summaries = []

    for path in _list_report_files():

        with open(path, "r", encoding="utf-8") as f:
            report = json.load(f)

        stats = report["verified_statistics"]

        severity_distribution = stats.get("severity_distribution", {})

        summaries.append({
            "name": path.stem,
            "generated_at": report["run_metadata"]["generated_at"],
            "flows_in_snapshot": report["run_metadata"]["flows_in_snapshot"],
            "attack_count": stats["attack_count"],
            "attack_rate_pct": stats["attack_rate_pct"],
            "overall_risk_level": stats["overall_risk_level"],
            "severity_distribution": severity_distribution,
            "critical_count": severity_distribution.get("Critical", 0),
        })

    return {"reports": summaries, "retention_limit": config.REPORTS_TO_KEEP}


@app.get("/api/reports/{name}")
def get_report(name: str):
    """
    Full JSON for one report, exactly as generate_report.py wrote it --
    verified_statistics, detailed_findings, llm_analysis, model, and
    run_metadata, unmodified.
    """

    if not REPORT_NAME_PATTERN.match(name):
        raise HTTPException(status_code=400, detail="Invalid report name")

    path = REPORTS_DIR / f"{name}.json"

    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
