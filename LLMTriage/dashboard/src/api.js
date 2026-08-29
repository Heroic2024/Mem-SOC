// Fetch helpers for the Stage 4 Report API (report_server.py).
//
// This is the ONLY place the dashboard talks to the backend, and it is
// read-only -- GET requests against already-computed report JSON. No
// statistics, no LLM calls, and no detection logic exist on this side;
// everything here does is fetch data that generate_report.py already
// wrote to disk.

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

async function getJSON(path) {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

// { reports: [{name, generated_at, flows_in_snapshot, attack_count,
//              attack_rate_pct, overall_risk_level}, ...], retention_limit }
export function listReports() {
  return getJSON("/api/reports");
}

// Full report: { run_metadata, verified_statistics, detailed_findings,
//                llm_analysis, model }
export function getReport(name) {
  return getJSON(`/api/reports/${name}`);
}
