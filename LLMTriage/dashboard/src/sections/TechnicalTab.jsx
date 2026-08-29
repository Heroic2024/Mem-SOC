import Panel from "../components/Panel";
import CategoryChart from "../components/CategoryChart";
import CategoryTable from "../components/CategoryTable";
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
      <Panel title="Attack Category Breakdown">
        <CategoryChart categoryBreakdown={stats.category_breakdown} />
        <CategoryTable rows={stats.category_breakdown} />
      </Panel>

      <div className="panel-grid-2">
        <Panel title="Confidence Distribution">
          <SimpleBarChart data={dictToChartData(stats.confidence_distribution)} order={CONFIDENCE_ORDER} />
        </Panel>
        <Panel title="Protocol Distribution">
          <SimpleBarChart data={dictToChartData(stats.protocol_distribution)} />
        </Panel>
      </div>

      <div className="panel-grid-2">
        <Panel title="Top Targeted Ports">
          <SimpleBarChart data={pairsToChartData(stats.top_targeted_ports)} />
        </Panel>
        <Panel title="Most Frequent SHAP Indicators">
          <SimpleBarChart data={pairsToChartData(stats.top_shap_indicators)} />
        </Panel>
      </div>

      <Panel title="Threat / Attack Analysis">
        <p className="panel-text">{llm.threat_analysis}</p>
      </Panel>

      <Panel title={`Detailed Findings (top ${findings.length}, ranked by risk score)`}>
        <FindingsTable findings={findings} />
      </Panel>
    </div>
  );
}
