export default function AlertJourney() {
  return (
    <section id="alert-journey" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="section-head">
        <div className="section-kicker">System</div>
        <h2>One alert's full journey</h2>
        <div className="section-desc">
          A single real alert traced through every script in the pipeline — the detector, the triage prompt
          builder, the memory layer and the live model call — for both experimental arms, side by side. Every
          number and every line of text in it is this alert's actual recorded data.
        </div>
      </div>
      <iframe
        src="/alert-journey.html"
        title="One alert's full journey through MemSOC"
        style={{ flex: 1, minHeight: 900, width: "100%", border: "1px solid var(--color-border)", borderRadius: 10, background: "#fbf0e4" }}
      />
    </section>
  );
}
