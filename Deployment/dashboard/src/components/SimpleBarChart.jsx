import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, LabelList,
} from "recharts";
import { ACCENT, CHART_THEME } from "../constants";

// Generic bar chart used for confidence distribution, protocol
// distribution, top targeted ports, and top SHAP indicators -- the
// only thing that differs between those is the data and, for
// confidence, a fixed logical order instead of sort-by-value.
export default function SimpleBarChart({ data, order }) {
  if (!data || data.length === 0) return null;

  const chartData = order
    ? order.filter((key) => data.some((d) => d.name === key))
        .map((key) => data.find((d) => d.name === key))
    : data;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={chartData} margin={{ top: 20, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} vertical={false} />
        <XAxis dataKey="name" stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 12 }} />
        <YAxis stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 12 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: CHART_THEME.tooltipBg, border: `1px solid ${CHART_THEME.tooltipBorder}`, borderRadius: 8 }}
          labelStyle={{ color: CHART_THEME.label }}
        />
        <Bar dataKey="count" fill={ACCENT} radius={[4, 4, 0, 0]}>
          <LabelList dataKey="count" position="top" fill={CHART_THEME.label} fontWeight={700} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
