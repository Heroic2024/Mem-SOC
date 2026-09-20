import Panel from "../components/Panel";
import SeverityChart from "../components/SeverityChart";

export default function OverviewTab({ report }) {
  const stats = report.verified_statistics;
  const llm = report.llm_analysis;

  return (
    <div>
      <Panel title="Executive Summary">
        <p className="panel-text">{llm.executive_summary}</p>
      </Panel>

      <Panel
        title="Severity Distribution"
        caption="Every attack in this snapshot, categorized by risk level -- not just the sampled findings below."
      >
        {stats.severity_distribution ? (
          <SeverityChart distribution={stats.severity_distribution} />
        ) : (
          <div className="state-message">
            This report was generated before severity distribution was tracked.
            Run generate_report.py again to see this chart.
          </div>
        )}
      </Panel>

      <div className="panel-grid-2">
        <Panel title="Security Overview">
          <p className="panel-text">{llm.security_overview}</p>
        </Panel>
        <Panel title="Risk Analysis">
          <p className="panel-text">{llm.risk_analysis}</p>
        </Panel>
      </div>
    </div>
  );
}
