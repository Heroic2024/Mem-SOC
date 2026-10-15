export default function Sidebar({ reports, selected, onSelect, retentionLimit }) {
  return (
    <div className="sidebar">
      <div className="sidebar-title">MemSOC</div>
      <div className="sidebar-caption">
        {reports.length} report(s) available (latest {retentionLimit} kept)
      </div>
      <select
        className="report-select"
        value={selected || ""}
        onChange={(e) => onSelect(e.target.value)}
      >
        {reports.map((r) => (
          <option key={r.name} value={r.name}>
            {r.name.replace("security_report_", "")}
          </option>
        ))}
      </select>
      <hr className="sidebar-divider" />
      <div className="sidebar-note">
        This dashboard only reads report data from the Stage 4 API. It
        never triggers capture or report generation itself.
      </div>
    </div>
  );
}
