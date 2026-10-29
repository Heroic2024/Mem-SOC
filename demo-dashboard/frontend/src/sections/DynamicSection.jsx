import { useEffect, useState } from "react";
import { getDemoAlerts, liveTriage } from "../api.js";

function SimBar({ value }) {
  return (
    <div className="sim-bar-track">
      <div className="sim-bar-fill" style={{ width: `${value * 100}%` }} />
    </div>
  );
}

function ArmResult({ title, result, cls }) {
  if (!result) return null;
  return (
    <div className={`arm-panel ${cls}`}>
      <h3>{title}</h3>
      {result.fallback_to_recorded && (
        <div className="fallback-badge">live call failed — showing recorded result</div>
      )}
      <div style={{ marginTop: 8 }}>
        <span className={`badge ${result.verdict}`}>{result.verdict}</span>{" "}
        <strong>{result.attack_category}</strong>{" "}
        <span style={{ color: "#9aa0ab" }}>conf. {result.confidence}</span>
      </div>
      <p style={{ fontSize: 12, color: "#cfd3da" }}>{result.rationale_summary}</p>
      {result.live && <div style={{ fontSize: 11, color: "#9aa0ab" }}>live call: {result.latency_ms} ms</div>}
    </div>
  );
}

export default function DynamicSection() {
  const [demoAlerts, setDemoAlerts] = useState(null);
  const [model, setModel] = useState("gemma");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [revealStep, setRevealStep] = useState(0);

  useEffect(() => {
    getDemoAlerts().then(setDemoAlerts).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!result) return;
    setRevealStep(0);
    const steps = 6;
    let i = 0;
    const timer = setInterval(() => {
      i += 1;
      setRevealStep(i);
      if (i >= steps) clearInterval(timer);
    }, 450);
    return () => clearInterval(timer);
  }, [result]);

  async function pick(alert) {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await liveTriage(model, alert.uid);
      setResult(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="panel">
        <h2>Pick a model, then an alert</h2>
        <div className="model-tabs">
          {["gemma", "gptoss"].map((m) => (
            <button key={m} className={model === m ? "active" : ""} onClick={() => setModel(m)}>
              {m === "gemma" ? "Gemma 4 26B" : "gpt-oss-20b"}
            </button>
          ))}
        </div>
        {demoAlerts && (
          <div className="alert-picker">
            {demoAlerts[model].map((a) => (
              <button key={a.uid} onClick={() => pick(a)} disabled={loading}>
                <span className="label">{a.label}</span>
                <span className="note">{a.note}</span>
              </button>
            ))}
          </div>
        )}
        {loading && (
          <div style={{ marginTop: 10, color: "#9aa0ab" }}>
            <span className="loading-pulse" /> retrieving memory, then calling the real model
            {model === "gemma" ? " (Gemma can take 20–40s)" : " (usually 2–3s)"}…
          </div>
        )}
        {error && <div className="caveat">Error: {error}</div>}
      </div>

      {result && (
        <>
          {revealStep >= 1 && (
            <div className="panel step">
              <h2>Step 1–2 — The alert and its case text</h2>
              <p style={{ fontSize: 12, color: "#9aa0ab" }}>
                This is exactly what gets embedded for retrieval — the detector's label and score are deliberately
                excluded, so retrieval can never see the answer it's being asked to help with.
              </p>
              <pre className="precedent-card">{result.case_text}</pre>
            </div>
          )}

          {revealStep >= 2 && (
            <div className="panel step">
              <h2>Step 3–5 — Retrieval against the real memory store</h2>
              <p style={{ fontSize: 12, color: "#9aa0ab" }}>
                Vector search latency: {result.retrieval.latency_ms} ms (local, real ChromaDB store)
              </p>
              {result.retrieval.precedents.map((p, i) => (
                <div className="precedent-card" key={p.case_id}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <strong>#{i + 1} {p.case_id}</strong>
                    <span>{(p.similarity * 100).toFixed(1)}% similar</span>
                  </div>
                  <SimBar value={p.similarity} />
                  <pre>{p.document}</pre>
                  <div>
                    stored: <span className={`badge ${p.verdict}`}>{p.verdict}</span> {p.attack_category}, conf. {p.confidence}
                  </div>
                </div>
              ))}
              <div className="caveat">
                Similarity alone doesn't indicate a trustworthy match — this project's own retrieval analysis found
                correct and incorrect precedents score almost identically. Judge these by content, not by the bar.
              </div>
            </div>
          )}

          {revealStep >= 3 && (
            <div className="panel step">
              <h2>Step 6 — What gets injected into the prompt</h2>
              <pre className="precedent-card">{result.precedent_block}</pre>
            </div>
          )}

          {revealStep >= 4 && (
            <div className="panel step">
              <h2>Step 7 — Live verdicts, side by side</h2>
              <div className="arm-compare">
                <ArmResult title="Arm A — no memory" result={result.results.armA} cls="armA" />
                <ArmResult title="B-self — with memory" result={result.results.bself} cls="bself" />
              </div>
            </div>
          )}

          {revealStep >= 5 && result.mechanism_check && (
            <div className="panel step">
              <h2>Step 8 — Did it just copy?</h2>
              <p>
                Plurality family among the 3 retrieved precedents:{" "}
                <strong>{result.mechanism_check.plurality_family_of_precedents}</strong>. B-self's answer:{" "}
                <strong>{result.mechanism_check.bself_family}</strong>.{" "}
                {result.mechanism_check.matches_plurality ? (
                  <span className="match-badge">matches — the copying mechanism, live</span>
                ) : (
                  <span>did not match this time</span>
                )}
              </p>
            </div>
          )}

          {revealStep >= 6 && result.matches_recorded !== null && (
            <div className="panel step">
              <h2>Reproducibility check</h2>
              {result.matches_recorded ? (
                <span className="match-badge">this fresh live call reproduces the originally recorded result</span>
              ) : (
                <span className="fallback-badge">this live call differs from the recorded result (model output is not perfectly deterministic)</span>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
