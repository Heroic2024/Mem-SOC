export default function Architecture({ onNavigate }) {
  return (
    <section id="architecture">
      <div className="section-head">
        <div className="section-kicker">System</div>
        <h2>Architecture</h2>
        <div className="section-desc">The four-layer pipeline and the three experimental arms.</div>
      </div>
      <div className="two-col">
        <div className="panel">
          <h3>Four-layer pipeline</h3>
          <img src="/diagrams/four-layer-pipeline.png" alt="Four architectural layers and data flow" style={{ width: "100%", borderRadius: 8 }} />
          <div className="footnote">Layer 4 writes triaged cases back into Layer 3, which supplies precedent for later alerts.</div>
        </div>
        <div className="panel">
          <h3>Three experimental arms</h3>
          <img src="/diagrams/three-arms.png" alt="Arm A, B-self and B-oracle" style={{ width: "100%", borderRadius: 8 }} />
          <div className="footnote">B-self and B-oracle retrieve identical cases; only what was stored differs.</div>
        </div>
      </div>
      <div className="panel" style={{ marginTop: 20 }}>
        <h3>Want to see this traced through one real alert, script by script?</h3>
        <p className="section-desc" style={{ marginTop: 6 }}>
          The two diagrams above show the architecture in the abstract. The next section animates a single real
          alert moving through every script in it — the detector, the triage prompt builder, the memory layer,
          the live model call, both arms side by side — showing the actual real data at every step.
        </p>
        <button
          className="chip on"
          onClick={() => onNavigate?.("journey")}
          style={{ marginTop: 4, borderRadius: 7, fontSize: 13, padding: "8px 16px" }}
        >
          See one alert's full journey →
        </button>
      </div>
    </section>
  );
}
