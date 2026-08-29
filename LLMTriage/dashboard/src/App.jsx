import { useEffect, useState } from "react";
import { listReports, getReport } from "./api";
import Sidebar from "./components/Sidebar";
import KpiRow from "./components/KpiRow";
import Tabs from "./components/Tabs";
import OverviewTab from "./sections/OverviewTab";
import TechnicalTab from "./sections/TechnicalTab";
import ActionsTab from "./sections/ActionsTab";
import TrendsTab from "./sections/TrendsTab";

function Banner({ title, sub }) {
  return (
    <div className="banner">
      <div className="banner-title">{title}</div>
      {sub && <div className="banner-sub">{sub}</div>}
    </div>
  );
}

export default function App() {
  const [reports, setReports] = useState([]);
  const [retentionLimit, setRetentionLimit] = useState(5);
  const [selectedName, setSelectedName] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);

  // Fetch the report list once on mount.
  useEffect(() => {
    listReports()
      .then(({ reports, retention_limit }) => {
        setReports(reports);
        setRetentionLimit(retention_limit);
        if (reports.length > 0) {
          setSelectedName(reports[0].name);
        }
        setLoadingList(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoadingList(false);
      });
  }, []);

  // Fetch the full report whenever the selection changes.
  useEffect(() => {
    if (!selectedName) return;
    setLoadingReport(true);
    getReport(selectedName)
      .then((data) => {
        setReport(data);
        setLoadingReport(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoadingReport(false);
      });
  }, [selectedName]);

  if (error) {
    return (
      <div className="app-shell">
        <div className="main-content">
          <Banner title="MemSOC Security Dashboard" />
          <div className="state-message error">
            Could not reach the report API: {error}
            <br /><br />
            Make sure report_server.py is running:
            <br /><code>python -m uvicorn report_server:app --port 8001</code>
          </div>
        </div>
      </div>
    );
  }

  if (!loadingList && reports.length === 0) {
    return (
      <div className="app-shell">
        <div className="main-content">
          <Banner title="MemSOC Security Dashboard" sub="No reports found yet." />
          <div className="state-message">
            1. Start the detection API (see log_generation/README.md)<br />
            2. Run <code>python live_capture.py</code><br />
            3. Run <code>python generate_report.py</code><br /><br />
            Then refresh this page.
          </div>
        </div>
      </div>
    );
  }

  if (loadingList || loadingReport || !report) {
    return (
      <div className="app-shell">
        <div className="main-content">
          <div className="state-message">Loading report...</div>
        </div>
      </div>
    );
  }

  const meta = report.run_metadata;
  const model = report.model;

  return (
    <div className="app-shell">
      <Sidebar
        reports={reports}
        selected={selectedName}
        onSelect={setSelectedName}
        retentionLimit={retentionLimit}
      />

      <div className="main-content">
        <Banner
          title="MemSOC Security Report"
          sub={`Generated ${meta.generated_at} · ${meta.flows_in_snapshot} flows in this snapshot · Model: ${model.provider}/${model.model_id}`}
        />

        <KpiRow stats={report.verified_statistics} />

        <Tabs
          tabs={[
            { label: "Overview", content: <OverviewTab report={report} /> },
            { label: "Technical Findings", content: <TechnicalTab report={report} /> },
            { label: "Recommendations & Action Plan", content: <ActionsTab report={report} /> },
            { label: "Trends", content: <TrendsTab reports={reports} retentionLimit={retentionLimit} /> },
          ]}
        />
      </div>
    </div>
  );
}
