import { OutlineBadge } from "./Badge";

export default function TrendTable({ reports }) {
  const rows = [...reports].reverse();

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Report</th>
            <th>Attack Rate %</th>
            <th>Attack Count</th>
            <th>Overall Risk Level</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              <td>{r.name.replace("security_report_", "")}</td>
              <td>{r.attack_rate_pct}%</td>
              <td>{r.attack_count}</td>
              <td><OutlineBadge level={r.overall_risk_level} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
