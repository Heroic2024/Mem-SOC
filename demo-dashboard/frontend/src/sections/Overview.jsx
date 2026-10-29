function pct(x) {
  return x == null ? "—" : `${(x * 100).toFixed(1)}%`;
}

export default function Overview() {
  return (
    <section>
      <div className="hero">
        <div>
          <h1>Does persistent memory help an LLM triage SOC alerts?</h1>
          <div className="section-desc">
            Three models, one controlled experiment: a memoryless baseline against a self-memory arm,
            scored against ground truth on held-out NetFlow alerts.
          </div>
        </div>
        <div className="hero-meta">
          <div>Models <b>3</b></div>
          <div>Arms <b>A · B-self · B-oracle</b></div>
        </div>
      </div>

      <div className="kpi-grid">
        <div className="kpi good">
          <div className="val good">42 → 22</div>
          <div className="lbl">Gemma: attacks missed, memory off vs. on</div>
          <div className="sub">p = 1.1 × 10⁻⁵</div>
        </div>
        <div className="kpi good">
          <div className="val good">74.5% → 86.7%</div>
          <div className="lbl">Gemma recall, memory off vs. on</div>
          <div className="sub">cluster-bootstrap CI [+5.8, +22.2]</div>
        </div>
        <div className="kpi">
          <div className="val">97.6%</div>
          <div className="lbl">Self-memory copy rate on retrieved precedent</div>
          <div className="sub">the mechanism, measured directly</div>
        </div>
        <div className="kpi warn">
          <div className="val warn">54.5% → 23.6%</div>
          <div className="lbl">Gemma family accuracy, same comparison</div>
          <div className="sub">isolated by the oracle-memory arm</div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <h3>What this demonstration covers</h3>
        <p style={{ fontSize: 13.5, color: "var(--color-text-muted)", lineHeight: 1.6, margin: 0 }}>
          <strong style={{ color: "var(--color-text)" }}>Correctly Caught</strong> showcases real attacks
          both models' memory arm correctly identified. <strong style={{ color: "var(--color-text)" }}>Per-Model Results</strong> and{" "}
          <strong style={{ color: "var(--color-text)" }}>Cross-Model</strong> give the complete picture, every arm, every model.{" "}
          <strong style={{ color: "var(--color-text)" }}>The Mechanism</strong> explains why memory
          helped Gemma's recall and hurt its family-naming. <strong style={{ color: "var(--color-text)" }}>Statistical Rigor</strong> shows
          the checks run against overstating any of it. <strong style={{ color: "var(--color-text)" }}>Live Demo</strong> runs
          the real pipeline, live, against the real models.
        </p>
      </div>
    </section>
  );
}
