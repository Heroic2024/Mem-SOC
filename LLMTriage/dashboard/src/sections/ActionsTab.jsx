import Panel from "../components/Panel";

export default function ActionsTab({ report }) {
  const llm = report.llm_analysis;

  return (
    <div>
      <Panel title="Recommendations">
        <ol className="numbered-list">
          {llm.recommendations.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ol>
      </Panel>

      <Panel title="Prioritized Action Plan">
        <ul className="step-list">
          {llm.prioritized_action_plan.map((item, i) => (
            <li key={i}><strong>Step {i + 1}.</strong> {item}</li>
          ))}
        </ul>
      </Panel>

      <Panel title="Conclusion">
        <p className="panel-text">{llm.conclusion}</p>
      </Panel>
    </div>
  );
}
