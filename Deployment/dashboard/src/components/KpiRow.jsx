import { SolidBadge } from "./Badge";
import { SEVERITY_COLORS } from "../constants";

export default function KpiRow({ stats }) {
  const riskColor = SEVERITY_COLORS[stats.overall_risk_level] || "#64748b";

  return (
    <div className="kpi-row">
      <div className="kpi-card">
        <div className="kpi-value">{stats.total_flows_processed}</div>
        <div className="kpi-label">Total Flows</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-value">{stats.attack_count}</div>
        <div className="kpi-label">Attacks Detected</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-value">{stats.attack_rate_pct}%</div>
        <div className="kpi-label">Attack Rate</div>
      </div>
      <div className="kpi-card" style={{ borderTopColor: riskColor }}>
        <div className="kpi-value">
          <SolidBadge level={stats.overall_risk_level} />
        </div>
        <div className="kpi-label">Overall Risk Level</div>
      </div>
    </div>
  );
}
