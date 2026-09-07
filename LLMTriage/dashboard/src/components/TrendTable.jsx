import { Fragment } from "react";
import { OutlineBadge } from "./Badge";

const PERIOD_ORDER = ["Today", "Yesterday", "Within the Last Week", "1 Week Ago", "1 Month Ago", "Older"];

function periodOf(isoString) {
  const now = new Date();
  const then = new Date(isoString);

  const sameDay = (a, b) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();

  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);

  const diffDays = (now - then) / (1000 * 60 * 60 * 24);

  if (sameDay(now, then)) return "Today";
  if (sameDay(yesterday, then)) return "Yesterday";
  if (diffDays < 7) return "Within the Last Week";
  if (diffDays < 14) return "1 Week Ago";
  if (diffDays < 35) return "1 Month Ago";

  return "Older";
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleString([], {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function groupByPeriod(reports) {
  const groups = {};

  for (const r of reports) {
    const period = periodOf(r.generated_at);
    (groups[period] ||= []).push(r);
  }

  // Newest report first within each group.
  for (const period in groups) {
    groups[period].sort((a, b) => new Date(b.generated_at) - new Date(a.generated_at));
  }

  return groups;
}

export default function TrendTable({ reports }) {
  const groups = groupByPeriod(reports);

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Report Date</th>
            <th>Attack Count</th>
            <th>Critical Alerts</th>
            <th>Attack Rate %</th>
            <th>Overall Risk Level</th>
          </tr>
        </thead>
        <tbody>
          {PERIOD_ORDER.filter((period) => groups[period]).map((period) => (
            <Fragment key={period}>
              <tr className="trend-period-row">
                <td colSpan={5}>{period}</td>
              </tr>
              {groups[period].map((r) => (
                <tr key={r.name}>
                  <td>{formatDate(r.generated_at)}</td>
                  <td>{r.attack_count}</td>
                  <td>{r.critical_count ?? 0}</td>
                  <td>{r.attack_rate_pct}%</td>
                  <td><OutlineBadge level={r.overall_risk_level} /></td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
