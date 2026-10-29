import { useEffect, useState } from "react";
import { getStatic } from "../api.js";

export default function Mechanism() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getStatic("model_gemma").then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <section className="panel">Failed to load: {error}</section>;
  if (!data) return <section className="panel">Loading…</section>;

  const cr = data.copy_rate;

  return (
    <section id="mechanism">
      <div className="section-head">
        <div className="section-kicker">Why</div>
        <h2>The copying mechanism</h2>
        <div className="section-desc">
          Oracle memory isolates the cause: identical retrieval, correct labels instead of self-written
          ones. This is what explains both the recall gain and the family-accuracy drop.
        </div>
      </div>
      <div className="three-col">
        <div className="panel">
          <h3>Copy rate</h3>
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 28 }}>{cr.plurality_match_pct}%</div>
          <div className="footnote">B-self family matches the plurality of its 3 retrieved precedents ({cr.plurality_match} of {cr.n_with_precedent})</div>
        </div>
        <div className="panel">
          <h3>Counterfactual</h3>
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 28, color: "var(--color-text-faint)" }}>{cr.armA_counterfactual_pct}%</div>
          <div className="footnote">Same match rate under Arm A — no memory to copy from. The gap is caused by seeing the precedents.</div>
        </div>
        <div className="panel">
          <h3>Oracle recovery</h3>
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 28, color: "var(--color-accent)" }}>{data.arms.boracle.cat_accuracy ? (data.arms.boracle.cat_accuracy * 100).toFixed(1) : "—"}%</div>
          <div className="footnote">Family accuracy once stored labels are correct, not self-written</div>
        </div>
      </div>
      <div className="panel" style={{ marginTop: 16 }}>
        <h3>When all three precedents agree, B-self copies</h3>
        <div className="barset">
          <div className="bar-row">
            <span className="name">Copy rate</span>
            <div className="bar-track"><div className="bar-fill warn" style={{ width: `${cr.shared_family_copy_pct}%` }} /></div>
            <span className="num">{cr.shared_family_copy_pct}%</span>
          </div>
        </div>
        <div className="footnote">{cr.shared_family_copied} of {cr.shared_family_alerts} alerts where all 3 retrieved precedents shared one family — B-self copied it almost every time</div>
      </div>
    </section>
  );
}
