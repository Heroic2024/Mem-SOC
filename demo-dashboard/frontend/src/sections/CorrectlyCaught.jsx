import { useEffect, useState } from "react";
import { getStatic } from "../api.js";

function FamilyLine({ model, family, correct, confidence, trueFamily }) {
  return (
    <div className="verdict-row">
      <span className="model-chip">{model}</span>
      {family}
      {correct ? (
        <span className="check">✓</span>
      ) : (
        <span className="family-wrong">(ground truth: {trueFamily})</span>
      )}
      <span style={{ marginLeft: "auto", color: "var(--color-text-faint)" }}>conf. {confidence}</span>
    </div>
  );
}

export default function CorrectlyCaught() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    getStatic("true_positive_showcase").then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <section className="panel">Failed to load: {error}</section>;
  if (!data) return <section className="panel">Loading…</section>;

  const visible = showAll ? data.examples : data.examples.slice(0, 6);

  return (
    <section id="caught">
      <div className="section-head">
        <div className="section-kicker">Showcase</div>
        <h2>Correctly caught attacks</h2>
        <div className="section-desc">
          Real alerts both models' self-memory arm correctly escalated as genuine attacks (verdict ==
          true_positive). Filtered from the full result set, not separately curated. The checkmark means
          the model also named the right attack family — not every correct catch does, and that's shown
          honestly too.
        </div>
      </div>

      <div className="tp-banner">
        <div className="lbl">
          <strong style={{ color: "var(--color-text)" }}>{data.both_models_count}</strong> alerts both
          models correctly caught as real attacks, of which{" "}
          <strong style={{ color: "var(--color-text)" }}>{data.both_family_correct_count}</strong> also
          got the attack family right on both sides.
        </div>
        <div className="big">{data.both_models_count}</div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi good">
          <div className="val good">{data.gemma_count}</div>
          <div className="lbl">Gemma: total correct catches (of 165)</div>
        </div>
        <div className="kpi good">
          <div className="val good">{data.gptoss_count}</div>
          <div className="lbl">gpt-oss-20b: total correct catches (of 165)</div>
        </div>
      </div>

      <div className="tp-grid">
        {visible.map((e) => (
          <div className="tp-card" key={e.uid}>
            <div className="head">
              <span className="alert-id">
                #{e.seq_gemma} · {e.uid}
              </span>
              <span className="pill good">true positive</span>
            </div>
            <div className="family">{e.true_family || e.family_gemma}</div>
            <FamilyLine
              model="GEMMA"
              family={e.family_gemma}
              correct={e.family_gemma_correct}
              confidence={e.confidence_gemma}
              trueFamily={e.true_family}
            />
            <FamilyLine
              model="GPT-OSS-20B"
              family={e.family_gptoss}
              correct={e.family_gptoss_correct}
              confidence={e.confidence_gptoss}
              trueFamily={e.true_family}
            />
            <div className="rationale">{e.rationale_gemma}</div>
          </div>
        ))}
      </div>

      {!showAll && data.examples.length > 6 && (
        <div style={{ marginTop: 14 }}>
          <button className="pill neutral" style={{ cursor: "pointer", border: "none" }} onClick={() => setShowAll(true)}>
            browse all {data.examples.length}
          </button>
        </div>
      )}
    </section>
  );
}
