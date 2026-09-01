import { OutlineBadge } from "./Badge";

export default function FindingsTable({ findings }) {
  if (!findings || findings.length === 0) {
    return <div className="state-message">No attack findings in this snapshot.</div>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>UID</th>
            <th>Dst Port</th>
            <th>Protocol</th>
            <th>Category</th>
            <th>Confidence</th>
            <th>Risk Score</th>
            <th>Risk Level</th>
            <th>Top Indicators</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f) => (
            <tr key={f.uid}>
              <td>{f.uid}</td>
              <td>{f.dst_port}</td>
              <td>{f.protocol}</td>
              <td>{f.category}</td>
              <td>{f.confidence}</td>
              <td>{f.risk_score}</td>
              <td><OutlineBadge level={f.risk_level} /></td>
              <td>{f.top_indicators.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
