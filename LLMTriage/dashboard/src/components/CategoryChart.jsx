import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Cell, LabelList,
} from "recharts";
import { SEVERITY_COLORS, CHART_THEME } from "../constants";

export default function CategoryChart({ categoryBreakdown }) {
  if (!categoryBreakdown || categoryBreakdown.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={categoryBreakdown} margin={{ top: 20, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} vertical={false} />
        <XAxis dataKey="category" stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 12 }} />
        <YAxis stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 12 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: CHART_THEME.tooltipBg, border: `1px solid ${CHART_THEME.tooltipBorder}`, borderRadius: 8 }}
          labelStyle={{ color: CHART_THEME.label }}
        />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          <LabelList dataKey="count" position="top" fill={CHART_THEME.label} fontWeight={700} />
          {categoryBreakdown.map((entry) => (
            <Cell key={entry.category} fill={SEVERITY_COLORS[entry.risk_level] || "#64748b"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
