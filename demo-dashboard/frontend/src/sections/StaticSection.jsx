import { useEffect, useState } from "react";
import { getStatic } from "../api.js";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";

function pct(x) {
  return x == null ? "—" : `${(x * 100).toFixed(1)}%`;
}

function KpiTile({ label, value, tone }) {
  return (
    <div className={`kpi-tile ${tone || ""}`}>
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}

function ModelPanel({ data }) {
  if (!data) return null;
  const { arms, bself_vs_armA, copy_rate, consistency, label } = data;

  const recallData = [
    { arm: "Arm A", recall: arms.A.recall * 100 },
    { arm: "B-self", recall: arms.bself.recall * 100 },
    { arm: "B-oracle", recall: arms.boracle.recall * 100 },
  ];
  const famData = [
    { arm: "Arm A", acc: arms.A.cat_accuracy * 100 },
    { arm: "B-self", acc: arms.bself.cat_accuracy * 100 },
    { arm: "B-oracle", acc: arms.boracle.cat_accuracy * 100 },
  ];

  return (
    <>
      <div className="kpi-row">
        <KpiTile label={`${label}: Arm A recall`} value={pct(arms.A.recall)} />
        <KpiTile label="B-self recall" value={pct(arms.bself.recall)} tone={arms.bself.recall > arms.A.recall ? "good" : "bad"} />
        <KpiTile label="Arm A family accuracy" value={pct(arms.A.cat_accuracy)} />
        <KpiTile label="B-self family accuracy" value={pct(arms.bself.cat_accuracy)} tone={arms.bself.cat_accuracy > arms.A.cat_accuracy ? "good" : "bad"} />
      </div>

      <div className="panel">
        <h2>Recall and family accuracy by arm</h2>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={recallData.map((r, i) => ({ ...r, famAcc: famData[i].acc }))}>
            <CartesianGrid strokeDasharray="3 3" stroke="#262b35" />
            <XAxis dataKey="arm" stroke="#9aa0ab" />
            <YAxis stroke="#9aa0ab" unit="%" />
            <Tooltip contentStyle={{ background: "#171a21", border: "1px solid #2a2e38" }} />
            <Legend />
            <Bar dataKey="recall" name="Recall %" fill="#5b9dff" />
            <Bar dataKey="famAcc" name="Family accuracy %" fill="#e3b341" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {bself_vs_armA && (
        <div className="panel">
          <h2>Statistical rigor: B-self vs Arm A</h2>
          <table className="data-table">
            <thead>
              <tr><th>Metric</th><th>Point</th><th>Per-alert McNemar p</th><th>Per-alert bootstrap CI</th><th>Cluster-bootstrap CI</th><th>Cluster-bootstrap p</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>Recall</td>
                <td>{(bself_vs_armA.recall.per_alert_bootstrap.point * 100).toFixed(1)} pts</td>
                <td>{bself_vs_armA.recall.mcnemar.p.toExponential(2)}</td>
                <td>[{(bself_vs_armA.recall.per_alert_bootstrap.ci_lo * 100).toFixed(1)}, {(bself_vs_armA.recall.per_alert_bootstrap.ci_hi * 100).toFixed(1)}]</td>
                <td>[{(bself_vs_armA.recall.cluster_bootstrap.ci_lo * 100).toFixed(1)}, {(bself_vs_armA.recall.cluster_bootstrap.ci_hi * 100).toFixed(1)}]</td>
                <td>{bself_vs_armA.recall.cluster_bootstrap.p_empirical?.toFixed(4)}</td>
              </tr>
              <tr>
                <td>Family accuracy</td>
                <td>{(bself_vs_armA.cat_accuracy.per_alert_bootstrap.point * 100).toFixed(1)} pts</td>
                <td>{bself_vs_armA.cat_accuracy.mcnemar.p.toExponential(2)}</td>
                <td>[{(bself_vs_armA.cat_accuracy.per_alert_bootstrap.ci_lo * 100).toFixed(1)}, {(bself_vs_armA.cat_accuracy.per_alert_bootstrap.ci_hi * 100).toFixed(1)}]</td>
                <td>[{(bself_vs_armA.cat_accuracy.cluster_bootstrap.ci_lo * 100).toFixed(1)}, {(bself_vs_armA.cat_accuracy.cluster_bootstrap.ci_hi * 100).toFixed(1)}]</td>
                <td>{bself_vs_armA.cat_accuracy.cluster_bootstrap.p_empirical?.toFixed(4)}</td>
              </tr>
            </tbody>
          </table>
          <div className="caveat">
            The per-alert McNemar test assumes every alert is independent. Near-duplicate alerts are not — the
            cluster-bootstrap columns resample whole near-duplicate groups instead, which is why those intervals
            are wider and the implied significance is less extreme.
          </div>
        </div>
      )}

      {copy_rate && (
        <div className="panel">
          <h2>The copying mechanism</h2>
          <div className="kpi-row">
            <KpiTile label="B-self family matches plurality of retrieved precedents" value={pct(copy_rate.plurality_match_pct / 100)} />
            <KpiTile label="Same, under Arm A (no memory) — counterfactual" value={pct(copy_rate.armA_counterfactual_pct / 100)} />
            <KpiTile label="When all 3 precedents agree, B-self copies" value={pct(copy_rate.shared_family_copy_pct / 100)} />
          </div>
          <div className="caveat">
            High similarity does not mean a correct precedent — correct and incorrect retrievals score almost
            identically in this project's own retrieval-quality analysis. What changes the outcome is what was
            stored, not how similar it looked.
          </div>
        </div>
      )}

      {consistency && (
        <div className="panel">
          <h2>Consistency on near-duplicate alert groups</h2>
          <table className="data-table">
            <thead><tr><th>Arm</th><th>Groups (size &gt; 1)</th><th>Uniform verdict</th><th>Uniform family</th></tr></thead>
            <tbody>
              {Object.entries(consistency).map(([arm, c]) => (
                <tr key={arm}>
                  <td>{arm}</td><td>{c.groups_multi}</td><td>{c.consistent_verdict}</td><td>{c.consistent_category}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export default function StaticSection() {
  const [modelData, setModelData] = useState({});
  const [crossModel, setCrossModel] = useState(null);
  const [activeModel, setActiveModel] = useState("gemma");
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      getStatic("model_gemma"),
      getStatic("model_gptoss"),
      getStatic("cross_model"),
    ])
      .then(([gemma, gptoss, cross]) => {
        setModelData({ gemma, gptoss });
        setCrossModel(cross);
      })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="panel">Failed to load static data: {error}. Did you run static_export.py?</div>;
  if (!modelData.gemma) return <div className="panel">Loading…</div>;

  return (
    <div>
      <div className="panel">
        <h2>Headline finding</h2>
        <p>
          On Gemma 4 26B, self-memory cut missed attacks nearly in half (42 → 22 of 165), a statistically
          significant and cluster-robust gain. The same memory cut family-labelling accuracy from 54.5% to 23.6% —
          the model was repeating the family of its retrieved precedents rather than evaluating each alert
          independently. The same mechanism appears on gpt-oss-20b too, though there it hurts both measures. The
          effect depends on the model, not on whether memory is used at all.
        </p>
      </div>

      <div className="model-tabs">
        {Object.entries(modelData).map(([key, d]) => (
          <button key={key} className={activeModel === key ? "active" : ""} onClick={() => setActiveModel(key)}>
            {d.label}
          </button>
        ))}
      </div>

      <ModelPanel data={modelData[activeModel]} />
    </div>
  );
}
