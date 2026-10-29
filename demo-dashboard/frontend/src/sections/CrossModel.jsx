import { useEffect, useState } from "react";
import { getStatic } from "../api.js";

function pct(x) {
  return x == null ? "—" : `${(x * 100).toFixed(1)}%`;
}

export default function CrossModel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getStatic("cross_model").then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <section className="panel">Failed to load: {error}</section>;
  if (!data) return <section className="panel">Loading…</section>;

  const { gemma, gptoss, qwen } = data.models;
  const gemmaDelta = gemma.arms.bself.recall - gemma.arms.A.recall;
  const gptossDelta = gptoss.arms.bself.recall - gptoss.arms.A.recall;

  return (
    <section id="cross-model">
      <div className="section-head">
        <div className="section-kicker">Comparison</div>
        <h2>Cross-model comparison</h2>
        <div className="section-desc">
          The same memory design, three models. The effect depends on the model — shown directly, not
          averaged away.
        </div>
      </div>
      <div className="panel">
        <table className="data-table">
          <thead>
            <tr>
              <th>Model</th>
              <th className="num">Recall, A</th>
              <th className="num">Recall, B-self</th>
              <th className="num">Δ recall</th>
              <th>Cluster-significant</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{gemma.label}</td>
              <td className="num">{pct(gemma.arms.A.recall)}</td>
              <td className="num">{pct(gemma.arms.bself.recall)}</td>
              <td className="num" style={{ color: gemmaDelta > 0 ? "var(--color-good)" : "var(--color-warn)" }}>
                {gemmaDelta > 0 ? "+" : ""}{(gemmaDelta * 100).toFixed(1)}
              </td>
              <td><span className="sig-dot good" />yes</td>
            </tr>
            <tr>
              <td>{gptoss.label}</td>
              <td className="num">{pct(gptoss.arms.A.recall)}</td>
              <td className="num">{pct(gptoss.arms.bself.recall)}</td>
              <td className="num" style={{ color: gptossDelta > 0 ? "var(--color-good)" : "var(--color-warn)" }}>
                {gptossDelta > 0 ? "+" : ""}{(gptossDelta * 100).toFixed(1)}
              </td>
              <td><span className="sig-dot warn" />no (cluster-bootstrap crosses zero)</td>
            </tr>
            <tr>
              <td>{qwen.label}</td>
              <td className="num">{pct(qwen.arms.A.recall)}</td>
              <td className="num">{pct(qwen.arms.bself.recall)}</td>
              <td className="num">
                {((qwen.arms.bself.recall - qwen.arms.A.recall) * 100).toFixed(1)}
              </td>
              <td><span className="sig-dot warn" />floor effect</td>
            </tr>
          </tbody>
        </table>
        <div className="callout" style={{ marginTop: 14 }}>
          <strong>Why Qwen is different:</strong> {qwen.note}
        </div>
      </div>
    </section>
  );
}
