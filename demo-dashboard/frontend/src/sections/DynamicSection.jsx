import { useEffect, useState } from "react";
import { getDemoAlerts, liveTriage, getStatic } from "../api.js";

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
        <span style={{ color: "var(--color-text-muted)" }}>conf. {result.confidence}</span>
      </div>
      <p style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{result.rationale_summary}</p>
      {result.live && <div style={{ fontSize: 11, color: "var(--color-text-muted)" }}>live call: {result.latency_ms} ms</div>}
    </div>
  );
}

function ConfirmedCatchesBrowser({ onReplay, loading }) {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("both");

  useEffect(() => {
    getStatic("true_positive_showcase").then(setData).catch(() => {});
  }, []);

  if (!data) return null;

  const rows = data.examples.slice(0, 25);

  return (
    <div className="panel" style={{ marginTop: 32 }}>
      <h3>Confirmed catches browser</h3>
      <div className="section-desc" style={{ marginBottom: 12 }}>
        Every real alert both models correctly caught, pulled straight from the scored results — click
        replay to run that exact alert live above.
      </div>
      <div className="browser-toolbar">
        <span className={`chip ${filter === "both" ? "on" : ""}`} onClick={() => setFilter("both")}>
          Verdict: true positive
        </span>
        <span className="chip">{data.both_models_count} both models</span>
        <span className="chip">{data.both_family_correct_count} family also correct</span>
      </div>
      <table className="data-table browser-table">
        <thead>
          <tr>
            <th>Alert</th>
            <th>Family</th>
            <th>Gemma conf.</th>
            <th>gpt-oss conf.</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.uid}>
              <td className="num" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>#{r.seq_gemma}</td>
              <td>{r.true_family || r.family_gemma}</td>
              <td>
                <span className="conf-bar"><i style={{ width: `${r.confidence_gemma * 100}%` }} /></span>
                {r.confidence_gemma}
              </td>
              <td>
                <span className="conf-bar"><i style={{ width: `${r.confidence_gptoss * 100}%` }} /></span>
                {r.confidence_gptoss}
              </td>
              <td>
                <button className="replay" disabled={loading} onClick={() => onReplay(r.uid, "gemma")}>
                  replay (Gemma)
                </button>{" "}
                <button className="replay" disabled={loading} onClick={() => onReplay(r.uid, "gptoss")}>
                  replay (gpt-oss)
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="footnote">{data.gemma_count} confirmed Gemma catches, {data.gptoss_count} confirmed gpt-oss-20b catches in total — showing first 25 of the overlap</div>
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
  const [showFullPicture, setShowFullPicture] = useState(false);

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

  async function pick(alert, modelOverride) {
    const useModel = modelOverride || model;
    if (modelOverride) setModel(modelOverride);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await liveTriage(useModel, alert.uid);
      setResult(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
    document.getElementById("dynamic-top")?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <div id="dynamic-top">
      <div className="section-head">
        <div className="section-kicker">Live</div>
        <h2>Dynamic demo</h2>
        <div className="section-desc">
          Pick a model and alert, watch retrieval and the live verdict happen in real time.
        </div>
      </div>
      <div className="panel">
        <h2>Pick a model, then an alert</h2>
        <div className="model-tabs">
          {["gemma", "gptoss"].map((m) => (
            <button key={m} className={model === m ? "active" : ""} onClick={() => setModel(m)}>
              {m === "gemma" ? "Gemma 4 26B" : "gpt-oss-20b"}
            </button>
          ))}
        </div>
        {demoAlerts && (() => {
          const alerts = demoAlerts[model];
          const helpAlerts = alerts.filter((a) => a.outcome && a.outcome.startsWith("help"));
          // Everything that isn't a clean "help" case (harm or neutral) is
          // held back from the default view, not just the harm-labelled ones.
          const restAlerts = alerts.filter((a) => !a.outcome || !a.outcome.startsWith("help"));
          const AlertButton = (a) => (
            <button key={a.uid} onClick={() => pick(a)} disabled={loading}>
              <span className="label">{a.label}</span>
              <span
                className={`pill ${a.outcome.startsWith("harm") ? "warn" : a.outcome.startsWith("help") ? "good" : "neutral"}`}
                style={{ display: "inline-block", marginTop: 6 }}
              >
                {a.outcome}
              </span>
              <span className="note">{a.note}</span>
            </button>
          );
          return (
            <>
              <div className="alert-picker">{helpAlerts.map(AlertButton)}</div>
              {restAlerts.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <button
                    className="chip"
                    style={{ cursor: "pointer" }}
                    onClick={() => setShowFullPicture((v) => !v)}
                  >
                    {showFullPicture ? "hide" : "show"} the full picture ({restAlerts.length} more, including where memory changed a verdict)
                  </button>
                  {showFullPicture && <div className="alert-picker" style={{ marginTop: 10 }}>{restAlerts.map(AlertButton)}</div>}
                </div>
              )}
            </>
          );
        })()}
        {loading && (
          <div style={{ marginTop: 10, color: "var(--color-text-muted)" }}>
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
              <p style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                This is exactly what gets embedded for retrieval — the detector's label and score are deliberately
                excluded, so retrieval can never see the answer it's being asked to help with.
              </p>
              <pre className="precedent-card">{result.case_text}</pre>
            </div>
          )}

          {revealStep >= 2 && (
            <div className="panel step">
              <h2>Step 3–5 — Retrieval against the real memory store</h2>
              <p style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
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

      <ConfirmedCatchesBrowser onReplay={(uid, m) => pick({ uid }, m)} loading={loading} />
    </div>
  );
}
