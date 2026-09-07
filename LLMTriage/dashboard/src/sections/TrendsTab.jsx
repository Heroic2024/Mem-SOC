import Panel from "../components/Panel";
import SeverityTrendChart from "../components/SeverityTrendChart";
import TrendTable from "../components/TrendTable";

export default function TrendsTab({ reports, retentionLimit }) {
  if (reports.length < 2) {
    return (
      <div className="state-message">
        Trend view needs at least 2 generated reports. Currently have {reports.length}.
        Run generate_report.py again later to build a trend (up to the {retentionLimit} most
        recent are kept).
      </div>
    );
  }

  return (
    <div>
      <Panel
        title="How Attack Rate Is Calculated"
        caption="Applies to every attack-related figure on this page and throughout the dashboard."
      >
        <p className="panel-text">
          Attack rate is the percentage of processed flows the detection model classified as an
          attack: <code>(attack_count / total_flows_processed) x 100</code>. A flow counts as an
          attack the moment the model's binary classifier assigns it that status -- the multiclass
          model then further categorizes it, and SHAP explains the classification. This count comes
          directly from the model's own output as captured in <code>live_results.jsonl</code>; it is
          not independently verified against ground truth at this stage. Because every report in
          this dashboard replays the same underlying dataset, the attack rate itself stays close to
          constant across reports -- the more informative signal is how the <em>composition</em> of
          risk within that rate shifts, which the chart below tracks instead.
        </p>
      </Panel>

      <Panel
        title="Severity Composition Across Recent Reports"
        caption="Each bar is one report, normalized to 100%, showing what share of that report's attacks fell into each risk level -- not the raw attack rate, which stays roughly flat across replays of the same dataset."
      >
        <SeverityTrendChart reports={reports} />
      </Panel>

      <Panel
        title="Risk Level History"
        caption="The most recent reports, labeled by when they were generated rather than by filename."
      >
        <TrendTable reports={reports} />
      </Panel>
    </div>
  );
}
