import Panel from "../components/Panel";
import TrendChart from "../components/TrendChart";
import TrendTable from "../components/TrendTable";

export default function TrendsTab({ reports, retentionLimit }) {
  if (reports.length < 2) {
    return (
      <div className="state-message">
        Trend view needs at least 2 generated reports. Currently have {reports.length}.
        Run generate_report.py again later to build a trend (up to the {retentionLimit} most
        recent are kept).
      </div>
    );
  }

  return (
    <div>
      <Panel title={`Attack Rate Across the ${reports.length} Most Recent Reports`}>
        <TrendChart reports={reports} />
      </Panel>
      <Panel title="Overall Risk Level History">
        <TrendTable reports={reports} />
      </Panel>
    </div>
  );
}
