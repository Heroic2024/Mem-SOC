import {
  ScatterChart, Scatter, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Cell, LabelList,
} from "recharts";
import { SEVERITY_COLORS, CHART_THEME } from "../constants";

function ScatterTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;

  const d = payload[0].payload;

  return (
    <div style={{
      background: CHART_THEME.tooltipBg,
      border: `1px solid ${CHART_THEME.tooltipBorder}`,
      borderRadius: 8,
      padding: "8px 12px",
      fontSize: 12,
      color: CHART_THEME.label,
    }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.category}</div>
      <div>Attacks: {d.count}</div>
      <div>Risk score: {d.risk_score}</div>
      <div>Risk level: {d.risk_level}</div>
    </div>
  );
}

// Relates how OFTEN a category occurs to how SEVERE it is -- the two
// axes stats_engine.py already computes independently, but neither the
// category chart nor the confidence chart shows how they relate to each
// other. A category in the upper right (frequent AND severe) is the
// clearest priority signal on the page.
export default function CategoryRiskScatter({ categoryBreakdown }) {
  if (!categoryBreakdown || categoryBreakdown.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ScatterChart margin={{ top: 20, right: 20, left: 10, bottom: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
        <XAxis
          type="number" dataKey="count" name="Number of Attacks"
          stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 12 }}
          label={{ value: "Number of Attacks", position: "insideBottom", offset: -10, fill: CHART_THEME.tick, fontSize: 11 }}
        />
        <YAxis
          type="number" dataKey="risk_score" name="Risk Score" domain={[0, 1]}
          stroke={CHART_THEME.axis} tick={{ fill: CHART_THEME.tick, fontSize: 12 }}
          label={{ value: "Risk Score", angle: -90, position: "insideLeft", fill: CHART_THEME.tick, fontSize: 11 }}
        />
        <Tooltip content={<ScatterTooltip />} />
        <Scatter data={categoryBreakdown}>
          <LabelList dataKey="category" position="top" style={{ fontSize: 10, fill: CHART_THEME.tick }} />
          {categoryBreakdown.map((entry) => (
            <Cell key={entry.category} fill={SEVERITY_COLORS[entry.risk_level] || "#64748b"} r={7} />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}
