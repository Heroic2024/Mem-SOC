import { useEffect, useState } from "react";
import { getStatic } from "../api.js";
import Donut from "../components/Donut.jsx";
import Histogram from "../components/Histogram.jsx";

function pct(x) {
  return x == null ? "—" : `${(x * 100).toFixed(1)}%`;
}
function ms(x) {
  return x == null ? "—" : x > 1000 ? `${(x / 1000).toFixed(1)}s` : `${Math.round(x)}ms`;
}

function ModelPanel({ data }) {
  const { arms, family_breakdown, confidence_histogram } = data;
  const donutData = Object.entries(family_breakdown || {})
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => ({ label, value }));

  return (
    <>
      <div className="kpi-grid">
        <div className="kpi">
          <div className="val">{pct(arms.A.recall)}</div>
          <div className="lbl">Arm A recall</div>
        </div>
        <div className={`kpi ${arms.bself.recall > arms.A.recall ? "good" : "warn"}`}>
          <div className={`val ${arms.bself.recall > arms.A.recall ? "good" : "warn"}`}>{pct(arms.bself.recall)}</div>
          <div className="lbl">B-self recall</div>
        </div>
        <div className="kpi">
          <div className="val">{pct(arms.A.cat_accuracy)}</div>
          <div className="lbl">Arm A family accuracy</div>
        </div>
        <div className={`kpi ${arms.bself.cat_accuracy > arms.A.cat_accuracy ? "good" : "warn"}`}>
          <div className={`val ${arms.bself.cat_accuracy > arms.A.cat_accuracy ? "good" : "warn"}`}>
            {pct(arms.bself.cat_accuracy)}
          </div>
          <div className="lbl">B-self family accuracy</div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <h3>Recall and family accuracy by arm</h3>
        <div className="barset">
          <div className="bar-row"><span className="name">A — recall</span><div className="bar-track"><div className="bar-fill faint" style={{ width: `${arms.A.recall * 100}%` }} /></div><span className="num">{pct(arms.A.recall)}</span></div>
          <div className="bar-row"><span className="name">B-self — recall</span><div className="bar-track"><div className="bar-fill good" style={{ width: `${arms.bself.recall * 100}%` }} /></div><span className="num">{pct(arms.bself.recall)}</span></div>
          <div className="bar-row"><span className="name">B-oracle — recall</span><div className="bar-track"><div className="bar-fill accent" style={{ width: `${arms.boracle.recall * 100}%` }} /></div><span className="num">{pct(arms.boracle.recall)}</span></div>
          <div className="bar-row" style={{ marginTop: 6 }}><span className="name">A — family</span><div className="bar-track"><div className="bar-fill faint" style={{ width: `${arms.A.cat_accuracy * 100}%` }} /></div><span className="num">{pct(arms.A.cat_accuracy)}</span></div>
          <div className="bar-row"><span className="name">B-self — family</span><div className="bar-track"><div className="bar-fill warn" style={{ width: `${arms.bself.cat_accuracy * 100}%` }} /></div><span className="num">{pct(arms.bself.cat_accuracy)}</span></div>
          <div className="bar-row"><span className="name">B-oracle — family</span><div className="bar-track"><div className="bar-fill accent" style={{ width: `${arms.boracle.cat_accuracy * 100}%` }} /></div><span className="num">{pct(arms.boracle.cat_accuracy)}</span></div>
        </div>
      </div>

      <div className="two-col" style={{ marginTop: 16 }}>
        <div className="panel">
          <h3>Attack families caught, B-self</h3>
          {donutData.length ? (
            <Donut data={donutData} />
          ) : (
            <div className="footnote">No correct catches to break down.</div>
          )}
          <div className="footnote">By family named for every alert B-self correctly escalated (verdict = true_positive)</div>
        </div>
        <div className="panel">
          <h3>Confidence on correct catches</h3>
          {confidence_histogram && (
            <Histogram labels={confidence_histogram.labels} counts={confidence_histogram.counts} />
          )}
          <div className="footnote">Confidence distribution among B-self's correct escalations</div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <h3>Mean latency per alert, by arm</h3>
        <div className="latency-row">
          <span className="name">Per alert</span>
          <div className="latency-pill"><span className="dot before" />Arm A <span className="v">{ms(arms.A.mean_latency_ms)}</span></div>
          <div className="latency-pill"><span className="dot after" />B-self <span className="v" style={{ color: "var(--color-accent)" }}>{ms(arms.bself.mean_latency_ms)}</span></div>
        </div>
        <div className="footnote">A retrieved precedent gives the model an answer to start from, so it reasons less from scratch (Section 4.4.5)</div>
      </div>
    </>
  );
}

export default function PerModelResults() {
  const [modelData, setModelData] = useState({});
  const [active, setActive] = useState("gemma");
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([getStatic("model_gemma"), getStatic("model_gptoss")])
      .then(([gemma, gptoss]) => setModelData({ gemma, gptoss }))
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <section className="panel">Failed to load: {error}</section>;
  if (!modelData.gemma) return <section className="panel">Loading…</section>;

  return (
    <section id="per-model">
      <div className="section-head">
        <div className="section-kicker">Results</div>
        <h2>Per-model results</h2>
        <div className="section-desc">Full metrics for each model, every arm.</div>
      </div>

      <div className="model-tabs">
        {Object.entries(modelData).map(([key, d]) => (
          <button key={key} className={active === key ? "active" : ""} onClick={() => setActive(key)}>
            {d.label}
          </button>
        ))}
      </div>

      <ModelPanel data={modelData[active]} />
    </section>
  );
}
