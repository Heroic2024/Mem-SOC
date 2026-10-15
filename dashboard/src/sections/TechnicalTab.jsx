import Panel from "../components/Panel";
import CategoryChart from "../components/CategoryChart";
import CategoryTable from "../components/CategoryTable";
import CategoryRiskScatter from "../components/CategoryRiskScatter";
import SimpleBarChart from "../components/SimpleBarChart";
import FindingsTable from "../components/FindingsTable";
import { pairsToChartData, dictToChartData } from "../utils";
import { CONFIDENCE_ORDER } from "../constants";

export default function TechnicalTab({ report }) {
  const stats = report.verified_statistics;
  const findings = report.detailed_findings;
  const llm = report.llm_analysis;

  return (
    <div>
      <Panel
        title="Attack Categories by Volume and Risk"
        caption="Number of detected attacks per category, colored by computed risk level; the table lists each category's average confidence and risk score."
      >
        <CategoryChart categoryBreakdown={stats.category_breakdown} />
        <CategoryTable rows={stats.category_breakdown} />
      </Panel>

      <Panel
        title="Attack Frequency vs. Risk Severity by Category"
        caption="Each point is one attack category, plotted by how often it occurs (x-axis) against its computed risk score (y-axis). Categories in the upper right are both common and severe, and warrant the highest priority."
      >
        <CategoryRiskScatter categoryBreakdown={stats.category_breakdown} />
      </Panel>

      <div className="panel-grid-2">
        <Panel
          title="Detection Confidence Distribution"
          caption="How confident the model was across every flagged attack; a concentration toward 0.9-1.0 indicates the model is highly certain about most of what it flags."
        >
          <SimpleBarChart data={dictToChartData(stats.confidence_distribution)} order={CONFIDENCE_ORDER} />
        </Panel>
        <Panel
          title="Protocol Distribution Among Attacks"
          caption="Transport-layer protocols observed in flagged attack traffic."
        >
          <SimpleBarChart data={dictToChartData(stats.protocol_distribution)} />
        </Panel>
      </div>

      <div className="panel-grid-2">
        <Panel
          title="Top Targeted Destination Ports"
          caption="Destination ports most frequently targeted by flagged attacks -- useful for identifying which exposed services are drawing the most attention."
        >
          <SimpleBarChart data={pairsToChartData(stats.top_targeted_ports)} />
        </Panel>
        <Panel
          title="Top Contributing Features -- All Attacks"
          caption="How often each network-flow feature appears among the model's top explanatory (SHAP) factors, across every flagged attack regardless of severity."
        >
          <SimpleBarChart data={pairsToChartData(stats.top_shap_indicators)} />
        </Panel>
      </div>

      <Panel
        title="Top Contributing Features -- Critical and High-Severity Attacks Only"
        caption="The same SHAP-based analysis restricted to Critical- and High-severity attacks -- what specifically drives the model's most serious classifications, which can rank differently from the all-attacks view above."
      >
        {stats.critical_high_shap_indicators ? (
          <SimpleBarChart data={pairsToChartData(stats.critical_high_shap_indicators)} />
        ) : (
          <div className="state-message">
            This report was generated before this breakdown was tracked.
            Run generate_report.py again to see this chart.
          </div>
        )}
      </Panel>

      <Panel title="Threat / Attack Analysis">
        <p className="panel-text">{llm.threat_analysis}</p>
      </Panel>

      <Panel title={`Detailed Findings (top ${findings.length}, ranked by risk score)`}>
        <FindingsTable findings={findings} />
      </Panel>
    </div>
  );
}
