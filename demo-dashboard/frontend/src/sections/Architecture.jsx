export default function Architecture() {
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
    </section>
  );
}
