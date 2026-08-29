import {
  AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from "recharts";
import { ACCENT, CHART_THEME } from "../constants";

export default function TrendChart({ reports }) {
  // reports arrive newest-first from the API; reverse for a
  // left-to-right timeline (oldest on the left).
  const data = [...reports].reverse().map((r) => ({
    name: r.name.replace("security_report_", ""),
    rate: r.attack_rate_pct,
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ACCENT} stopOpacity={0.4} />
            <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} vertical={false} />
        <XAxis dataKey="name" stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 11 }} />
        <YAxis stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 12 }} unit="%" />
        <Tooltip
          contentStyle={{ background: CHART_THEME.tooltipBg, border: `1px solid ${CHART_THEME.tooltipBorder}`, borderRadius: 8 }}
          labelStyle={{ color: CHART_THEME.label }}
        />
        <Area
          type="monotone"
          dataKey="rate"
          name="Attack Rate %"
          stroke={ACCENT}
          strokeWidth={2.5}
          fill="url(#trendFill)"
          dot={{ r: 3, fill: ACCENT }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
