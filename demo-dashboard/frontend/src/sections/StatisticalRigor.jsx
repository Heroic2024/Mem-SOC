import { useEffect, useState } from "react";
import { getStatic } from "../api.js";

function p(n) {
  return n == null ? "—" : n < 0.001 ? n.toExponential(2) : n.toFixed(4);
}
function pts(x) {
  return `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}`;
}

function RigorTable({ label, bundle }) {
  if (!bundle) return null;
  const { recall, cat_accuracy } = bundle;
  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <h3>{label}: B-self vs. Arm A</h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th className="num">Point</th>
            <th className="num">McNemar p</th>
            <th>Per-alert CI</th>
            <th>Cluster-bootstrap CI</th>
            <th className="num">Cluster p</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Recall</td>
            <td className="num">{pts(recall.per_alert_bootstrap.point)}</td>
            <td className="num">{p(recall.mcnemar.p)}</td>
            <td>[{pts(recall.per_alert_bootstrap.ci_lo)}, {pts(recall.per_alert_bootstrap.ci_hi)}]</td>
            <td>[{pts(recall.cluster_bootstrap.ci_lo)}, {pts(recall.cluster_bootstrap.ci_hi)}]</td>
            <td className="num">{p(recall.cluster_bootstrap.p_empirical)}</td>
          </tr>
          <tr>
            <td>Family accuracy</td>
            <td className="num">{pts(cat_accuracy.per_alert_bootstrap.point)}</td>
            <td className="num">{p(cat_accuracy.mcnemar.p)}</td>
            <td>[{pts(cat_accuracy.per_alert_bootstrap.ci_lo)}, {pts(cat_accuracy.per_alert_bootstrap.ci_hi)}]</td>
            <td>[{pts(cat_accuracy.cluster_bootstrap.ci_lo)}, {pts(cat_accuracy.cluster_bootstrap.ci_hi)}]</td>
            <td className="num">{p(cat_accuracy.cluster_bootstrap.p_empirical)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export default function StatisticalRigor() {
  const [gemma, setGemma] = useState(null);
  const [gptoss, setGptoss] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([getStatic("model_gemma"), getStatic("model_gptoss")])
      .then(([g, p]) => {
        setGemma(g);
        setGptoss(p);
      })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <section className="panel">Failed to load: {error}</section>;
  if (!gemma) return <section className="panel">Loading…</section>;

  return (
    <section id="rigor">
      <div className="section-head">
        <div className="section-kicker">Credibility</div>
        <h2>Statistical rigor</h2>
        <div className="section-desc">
          Per-alert McNemar tests assume independence. Near-duplicate alerts aren't — so every headline
          effect is checked a second way.
        </div>
      </div>

      <div className="callout warn" style={{ marginBottom: 16 }}>
        <strong>Why this matters:</strong> the cluster bootstrap resamples whole near-duplicate groups, not
        individual alerts. It widens every interval — for Gemma, the recall gain and the family-accuracy
        drop both survive; for gpt-oss-20b, the cluster-bootstrap CI crosses zero on both metrics, meaning
        its per-alert p-values overstated the evidence. We show that finding directly, not just the
        favorable one.
      </div>

      <RigorTable label={gemma.label} bundle={gemma.bself_vs_armA} />
      <RigorTable label={gptoss.label} bundle={gptoss.bself_vs_armA} />
    </section>
  );
}
