"""
Stage 4 (Layer 4) aggregate security report generator.

This module NEVER calls the detection API and NEVER reads
log_generation/generated_logs.jsonl -- running the model is
live_capture.py's job exclusively. This module only reads whatever is
currently in model_outputs/live_results.jsonl (written by
live_capture.py) and builds a report from that snapshot.

Workflow:

    [live_capture.py -- run separately, once or continuously]
    log_generation/generated_logs.jsonl
      |  POST to the existing, unmodified /api/logs
      v
    model_outputs/live_results.jsonl        <-- the hand-off file
      |
      | (this script reads it any time -- while capture is still
      |  running, or after it has stopped)
      v
    stats_engine.read_live_results()   -->  whatever has been captured so far
      |
      v
    stats_engine.compute_statistics()  -->  verified statistics   (pure Python)
    stats_engine.build_findings()      -->  ranked findings       (pure Python)
      |
      v
    report_prompt.render()             -->  prompt: verified stats + findings sample
      |
      v
    llm_client.call_groq()             -->  LLM interpretation, narrative only
      |
      v
    report_prompt.parse_llm_response() -->  validated narrative dict
      |
      v
    assemble + write                   -->  reports/security_report_<ts>.json / .md

Every number in the report comes from stats_engine.py. The LLM never
computes a statistic -- it writes the executive summary, risk analysis,
threat analysis, recommendations, prioritized action plan, and
conclusion, using only the verified numbers it was given.

Usage:

    python generate_report.py                # report over everything captured so far
    python generate_report.py --limit 500     # report over only the 500 most recently
                                               #   captured flows
    python generate_report.py --max-findings 40
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
import llm_client
import report_prompt
import stats_engine

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


# ---------------------------------------------------------------------
# Markdown rendering -- every section here is either a direct table of
# stats_engine.py's output (labelled as such) or the LLM's narrative
# text (also labelled as such). The two are never merged into a single
# unlabelled block.
# ---------------------------------------------------------------------
def _category_table(rows):

    header = "| Category | Count | % of Attacks | Avg Confidence | Risk Score | Risk Level |\n"
    header += "|---|---|---|---|---|---|\n"

    lines = [header]

    for r in rows:
        lines.append(
            f"| {r['category']} | {r['count']} | {r['pct_of_attacks']}% | "
            f"{r['avg_confidence']} | {r['risk_score']} | {r['risk_level']} |\n"
        )

    return "".join(lines)


def _counter_table(pairs, col_name):

    header = f"| {col_name} | Count |\n|---|---|\n"

    return header + "".join(f"| {k} | {v} |\n" for k, v in pairs)


def _findings_table(findings):

    header = (
        "| UID | Dst Port | Protocol | Category | Confidence | Risk Score | "
        "Risk Level | Top Indicators |\n"
        "|---|---|---|---|---|---|---|---|\n"
    )

    lines = [header]

    for f in findings:
        indicators = ", ".join(f["top_indicators"])
        lines.append(
            f"| {f['uid']} | {f['dst_port']} | {f['protocol']} | {f['category']} | "
            f"{f['confidence']} | {f['risk_score']} | {f['risk_level']} | {indicators} |\n"
        )

    return "".join(lines)


def _list_block(items):
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, start=1))


def render_markdown(report: dict) -> str:

    stats = report["verified_statistics"]
    findings = report["detailed_findings"]
    llm = report["llm_analysis"]
    meta = report["run_metadata"]
    model = report["model"]

    return f"""# MemSOC Security Report

**Generated:** {meta['generated_at']}
**Source:** `{meta['source_file']}` -- {meta['flows_in_snapshot']} flows in this snapshot
**Analysis model:** {model['provider']} / {model['model_id']} ({model['latency_ms']:.0f} ms)

---

## 1. Executive Summary

{llm['executive_summary']}

---

## 2. Security Overview

{llm['security_overview']}

**Traffic summary (verified statistics):**

| Metric | Value |
|---|---|
| Total flows in this snapshot | {stats['total_flows_processed']} |
| Benign flows | {stats['benign_count']} |
| Attack flows | {stats['attack_count']} |
| Attack rate | {stats['attack_rate_pct']}% |
| Distinct attack categories | {stats['distinct_attack_categories']} |
| Overall risk level | {stats['overall_risk_level']} |

---

## 3. Statistics (Programmatically Computed)

### 3.1 Severity Distribution (All Attacks)

{_counter_table([(level, stats['severity_distribution'][level]) for level in stats['severity_distribution']], "Severity")}

### 3.2 Attack Category Breakdown

{_category_table(stats['category_breakdown'])}

### 3.3 Confidence Distribution

{_counter_table(stats['confidence_distribution'].items(), "Confidence Range")}

### 3.4 Protocol Distribution (Attack Traffic)

{_counter_table(stats['protocol_distribution'].items(), "Protocol")}

### 3.5 Top Targeted Destination Ports

{_counter_table(stats['top_targeted_ports'], "Destination Port")}

### 3.6 Most Frequent SHAP Indicators Across All Attacks

{_counter_table(stats['top_shap_indicators'], "Feature")}

---

## 4. Risk Analysis

{llm['risk_analysis']}

---

## 5. Detailed Findings

Top {len(findings)} highest-risk flows in this snapshot, ranked by computed `risk_score`.

{_findings_table(findings)}

---

## 6. Threat / Attack Analysis

{llm['threat_analysis']}

---

## 7. Recommendations

{_list_block(llm['recommendations'])}

---

## 8. Prioritized Action Plan

{_list_block(llm['prioritized_action_plan'])}

---

## 9. Conclusion

{llm['conclusion']}

---

## Methodology

- **Statistics** (Section 2's table, Section 3, and Section 5) are
  computed directly in `stats_engine.py` from records that
  `live_capture.py` captured from the existing, unmodified detection
  pipeline (`final_ml_model_v1`). This script never calls that pipeline
  itself and never computes a statistic from raw data -- it only reads
  `model_outputs/live_results.jsonl`.
- **`risk_score`** = detector confidence x a fixed severity weight per
  attack category (see `SEVERITY_WEIGHTS` in `stats_engine.py`). This is
  a documented heuristic, not a measured ground-truth value.
- **Narrative sections** (1, 2's prose, 4, 6, 7, 8, 9) are written by the
  LLM ({model['model_id']}), instructed to use only the verified
  statistics above and to introduce no new figures.
- This snapshot reflects flows captured up to {meta['generated_at']} and
  may not include the entire stream if `live_capture.py` was still
  running, stopped early, or `--limit` was used.
- This run does not use the memory layer (`docs/memory-layer/`) and does
  not score verdicts against `ground_truth.csv`.
"""


# ---------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------
def check_api_key() -> None:

    if config.GROQ_API_KEY == config.GROQ_API_KEY_PLACEHOLDER:

        print(
            "GROQ_API_KEY is not set.\n"
            "Set it as an environment variable, e.g.:\n"
            '  PowerShell : $env:GROQ_API_KEY = "your-key-here"\n'
            '  bash       : export GROQ_API_KEY="your-key-here"\n'
            "or replace the placeholder in LLMTriage/config.py directly "
            "(not recommended for anything you intend to commit).",
            file=sys.stderr,
        )
        sys.exit(1)


def prune_old_reports(keep: int = config.REPORTS_TO_KEEP) -> None:
    """
    Keep only the `keep` most recently generated report pairs; delete the
    rest. Filenames are security_report_<YYYYMMDD_HHMMSS>.{json,md}, so
    an alphabetical sort is also a chronological sort -- no timestamp
    parsing needed. Only files matching that exact pattern in
    REPORTS_DIR are ever touched.
    """

    json_reports = sorted(REPORTS_DIR.glob("security_report_*.json"))

    if len(json_reports) <= keep:
        return

    for json_path in json_reports[:-keep]:

        md_path = json_path.with_suffix(".md")

        json_path.unlink()

        if md_path.exists():
            md_path.unlink()

        print(f"Pruned old report: {json_path.stem} (keeping latest {keep})")


def write_report(report: dict) -> None:

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = f"security_report_{timestamp}"

    json_path = REPORTS_DIR / f"{stem}.json"
    md_path = REPORTS_DIR / f"{stem}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))

    print(f"\nWrote {json_path}")
    print(f"Wrote {md_path}")

    prune_old_reports()


def main():

    parser = argparse.ArgumentParser(
        description="Stage 4 aggregate security report generator"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only use the N most recently captured flows "
             "(default: everything captured so far)"
    )
    parser.add_argument(
        "--max-findings", type=int, default=config.FINDINGS_IN_REPORT,
        help="Max detailed findings to include in the report"
    )

    args = parser.parse_args()

    check_api_key()

    if not config.LIVE_RESULTS_PATH.exists():
        print(
            f"No captured model outputs found at {config.LIVE_RESULTS_PATH}.\n"
            "Run live_capture.py first (in a separate terminal):\n"
            "  python live_capture.py\n",
            file=sys.stderr,
        )
        sys.exit(1)

    results = stats_engine.read_live_results(config.LIVE_RESULTS_PATH, args.limit)

    if not results:
        print(
            f"{config.LIVE_RESULTS_PATH} exists but contains no usable "
            "records yet -- is live_capture.py still on its first flow?",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Read {len(results)} captured flows from {config.LIVE_RESULTS_PATH}")

    stats = stats_engine.compute_statistics(results)
    findings = stats_engine.build_findings(results, args.max_findings)

    print(
        f"{stats['attack_count']} attacks / {stats['total_flows_processed']} flows "
        f"({stats['attack_rate_pct']}%) -- sending statistics to the LLM for analysis ..."
    )

    prompt = report_prompt.render(stats, findings[: config.FINDINGS_IN_PROMPT])

    raw_text, latency_ms = llm_client.call_groq(prompt)

    narrative = report_prompt.parse_llm_response(raw_text)

    report = {
        "run_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_file": str(config.LIVE_RESULTS_PATH),
            "flows_in_snapshot": len(results),
            "limit": args.limit,
        },
        "verified_statistics": stats,
        "detailed_findings": findings,
        "llm_analysis": narrative,
        "model": {
            "provider": "groq",
            "model_id": config.GROQ_MODEL,
            "latency_ms": latency_ms,
        },
    }

    write_report(report)


if __name__ == "__main__":
    main()
