"""
Layer 4 report routes -- GET /health, GET /api/reports, GET /api/reports/{name}.

Was LLMTriage/report_server.py. Read-only by design: it does NO processing
of its own -- no statistics, no LLM calls, no detection. It never imports
stats_engine, report_prompt or llm_client. It only reads report files that
generate_report.py already wrote to disk and returns their contents, so a
report always reflects what the pipeline actually produced.

The reports directory now comes from paths.REPORTS_DIR rather than being
resolved relative to this file, so the source layout and the on-disk
output layout are no longer tied together.
"""

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from memsoc import paths
from memsoc.api import schemas
from memsoc.triage import config

router = APIRouter()

# Only the current report schema's naming convention is served. This also
# excludes sample-fuzzers_report.json, a stale file from an earlier,
# incompatible single-alert report format that predates the aggregate
# statistics redesign -- it has a different JSON shape entirely and was
# never meant to be read by this API.
REPORT_NAME_PATTERN = re.compile(r"^security_report_\d{8}_\d{6}$")


def _list_report_files():
    """Retained report files, newest first. Empty before the first run."""

    reports_dir = paths.REPORTS_DIR

    if not os.path.isdir(reports_dir):
        return []

    return sorted(
        Path(reports_dir).glob("security_report_*.json"), reverse=True
    )


@router.get("/health", response_model=schemas.ReportHealth)
def health():
    return {"status": "ok", "reports_dir": str(paths.REPORTS_DIR)}


@router.get("/api/reports", response_model=schemas.ReportList)
def list_reports():
    """
    Lightweight summary of every currently retained report, newest first --
    enough for the dashboard's report picker and trend view without
    transferring every report's full payload up front.
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


@router.get("/api/reports/{name}")
def get_report(name: str):
    """
    Full JSON for one report, exactly as generate_report.py wrote it --
    verified_statistics, detailed_findings, llm_analysis, model, and
    run_metadata, unmodified.
    """

    if not REPORT_NAME_PATTERN.match(name):
        raise HTTPException(status_code=400, detail="Invalid report name")

    path = Path(paths.REPORTS_DIR) / f"{name}.json"

    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
