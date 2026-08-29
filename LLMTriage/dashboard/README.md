# MemSOC Dashboard (React)

Presentation layer for Stage 4 security reports. Fetches from
`report_server.py` (must be running at `http://127.0.0.1:8001` by
default) and renders it — computes nothing itself.

## Run it

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

`VITE_API_URL` (optional env var) overrides the report API base URL,
default `http://127.0.0.1:8001`.

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
