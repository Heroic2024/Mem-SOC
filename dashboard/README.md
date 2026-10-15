# MemSOC Dashboard (React)

Presentation layer for Stage 4 security reports. Fetches from the report
API (`src/memsoc/api/routes_reports.py`) and renders it — computes
nothing itself.

## Run it

Deployed, it is served by nginx in the same container that proxies the
API, so there is nothing to configure:

```powershell
docker compose -f deploy/docker-compose.yml up -d
# http://localhost:8080
```

For local development against a running report service (default
`http://localhost:8001`):

```powershell
npm install       # one-time
npm run dev
```

Opens at `http://localhost:5173`. Requires `report_server.py` running
first — see `../README.md` for the full pipeline.

## Structure

```
src/
├── api.js              fetch() wrappers -- the only network code in the app
├── constants.js         severity colors/order, shared chart theme
├── utils.js              [pairs]/{dict} -> chart-data reshaping (no computation)
├── App.jsx               report list + selection state, tab layout
├── components/
│   ├── Badge.jsx          severity pill (solid + outline variants)
│   ├── Panel.jsx          bordered section card used throughout
│   ├── KpiRow.jsx         the 4 top-of-page metric cards
│   ├── Sidebar.jsx        report picker
│   ├── Tabs.jsx           tab navigation (no router needed for one page)
│   ├── SeverityChart.jsx  severity distribution bar chart
│   ├── CategoryChart.jsx  attack category breakdown bar chart
│   ├── SimpleBarChart.jsx generic bar chart (confidence/protocol/ports/SHAP)
│   ├── CategoryTable.jsx / FindingsTable.jsx / TrendTable.jsx
│   └── TrendChart.jsx     attack-rate-over-reports area chart
└── sections/
    ├── OverviewTab.jsx      executive summary, severity chart, risk analysis
    ├── TechnicalTab.jsx     category/confidence/protocol/port/SHAP charts, findings table
    ├── ActionsTab.jsx       recommendations, prioritized action plan, conclusion
    └── TrendsTab.jsx        multi-report trend (needs 2+ reports)
```

## Configuration

The report API base URL defaults to **`/services/report`** — a relative
path. In the deployed stack this container's own nginx proxies it to the
report service; in `npm run dev`, Vite proxies the same prefix (see
`vite.config.js`). So the same build works on any host and on any
published port, and the requests are same-origin.

| Env var | Applies to | Default | Purpose |
|---|---|---|---|
| `VITE_API_URL` | build | `/services/report` | Point the bundle at some other backend. Nothing in `deploy/` sets it. |
| `MEMSOC_REPORT_PROXY` | `npm run dev` | `http://localhost:8001` | Where the dev server forwards `/services/report`. |

The `/services/report` prefix must match the `location` block in
`deploy/nginx.conf` (backlog **BL-071**).

## Dependencies

- `react` / `react-dom` — required.
- `recharts` — the one charting library used for every chart on the
  page (bar, area). Chosen over hand-rolled SVG or a heavier
  dashboard framework because it's the most idiomatic, composable
  charting library for React and nothing else here needs charts a
  general-purpose library can't do.
- `vite` / `@vitejs/plugin-react` — dev server and build tooling.

No CSS framework, no state-management library, no router — a single
page with tab-based navigation and one shared stylesheet
(`src/index.css`) covers everything this dashboard needs.
