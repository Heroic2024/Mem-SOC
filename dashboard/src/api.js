// Fetch helpers for the Stage 4 Report API (src/memsoc/api/routes_reports.py).
//
// This is the ONLY place the dashboard talks to the backend, and it is
// read-only -- GET requests against already-computed report JSON. No
// statistics, no LLM calls, and no detection logic exist on this side;
// everything here does is fetch data that generate_report.py already
// wrote to disk.
//
// The default is a RELATIVE path, deliberately. The gateway (nginx in
// this same container) proxies /services/report/ to the report service,
// so the browser calls whatever host it already loaded the page from.
// An absolute URL here used to be baked in at build time, which meant:
//   - changing the published report port needed an image rebuild, and
//   - opening the dashboard from any other machine fetched "localhost"
//     on the VIEWER's machine, so the page loaded but stayed empty.
// Both go away with a relative path. It also makes the request
// same-origin, so the report API needs no CORS headers at all.
//
// In `npm run dev`, Vite's proxy (see vite.config.js) forwards the same
// prefix to the report service, so this one path works in both modes.
//
// VITE_API_URL still overrides it, for pointing a local dev server at
// some other backend. Nothing in deploy/ sets it any more.

const API_URL = import.meta.env.VITE_API_URL || "/services/report";

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
