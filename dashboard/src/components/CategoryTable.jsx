import { OutlineBadge } from "./Badge";

export default function CategoryTable({ rows }) {
  if (!rows || rows.length === 0) return null;

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Category</th>
            <th>Count</th>
            <th>% of Attacks</th>
            <th>Avg Confidence</th>
            <th>Severity Weight</th>
            <th>Risk Score</th>
            <th>Risk Level</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.category}>
              <td>{r.category}</td>
              <td>{r.count}</td>
              <td>{r.pct_of_attacks}%</td>
              <td>{r.avg_confidence}</td>
              <td>{r.severity_weight}</td>
              <td>{r.risk_score}</td>
              <td><OutlineBadge level={r.risk_level} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
