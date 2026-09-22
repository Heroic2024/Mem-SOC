import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer,
} from "recharts";
import { SEVERITY_ORDER, SEVERITY_COLORS, CHART_THEME } from "../constants";

// Shows how the COMPOSITION of risk changes across reports, normalized
// to 100% per report, rather than the raw attack rate -- the raw rate
// stays roughly flat when the same dataset is replayed, but the mix of
// Critical/High/Medium/Low within that rate can still shift and is the
// more informative signal.
export default function SeverityTrendChart({ reports }) {
  const data = [...reports].reverse().map((r) => {
    const dist = r.severity_distribution || {};
    const total = SEVERITY_ORDER.reduce((sum, level) => sum + (dist[level] || 0), 0);

    const row = { name: r.name.replace("security_report_", "") };

    SEVERITY_ORDER.forEach((level) => {
      row[level] = total > 0 ? Math.round(((dist[level] || 0) / total) * 1000) / 10 : 0;
    });

    return row;
  });

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} vertical={false} />
        <XAxis dataKey="name" stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 11 }} />
        <YAxis stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 12 }} unit="%" />
        <Tooltip
          contentStyle={{ background: CHART_THEME.tooltipBg, border: `1px solid ${CHART_THEME.tooltipBorder}`, borderRadius: 8 }}
          labelStyle={{ color: CHART_THEME.label }}
          formatter={(value) => `${value}%`}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: CHART_THEME.tick }} />
        {SEVERITY_ORDER.map((level) => (
          <Bar key={level} dataKey={level} stackId="severity" fill={SEVERITY_COLORS[level]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
