import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Cell, LabelList,
} from "recharts";
import { SEVERITY_ORDER, SEVERITY_COLORS, CHART_THEME } from "../constants";

export default function SeverityChart({ distribution }) {
  const data = SEVERITY_ORDER.map((level) => ({
    name: level,
    count: distribution[level] || 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 20, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} vertical={false} />
        <XAxis dataKey="name" stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 12 }} />
        <YAxis stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 12 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: CHART_THEME.tooltipBg, border: `1px solid ${CHART_THEME.tooltipBorder}`, borderRadius: 8 }}
          labelStyle={{ color: CHART_THEME.label }}
        />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          <LabelList dataKey="count" position="top" fill={CHART_THEME.label} fontWeight={700} />
          {data.map((entry) => (
            <Cell key={entry.name} fill={SEVERITY_COLORS[entry.name]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
