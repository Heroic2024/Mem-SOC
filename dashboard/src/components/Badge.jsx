import { SEVERITY_COLORS } from "../constants";

export function SolidBadge({ level }) {
  const color = SEVERITY_COLORS[level] || "#64748b";
  return (
    <span className="badge" style={{ backgroundColor: color }}>
      {level}
    </span>
  );
}

export function OutlineBadge({ level }) {
  const color = SEVERITY_COLORS[level] || "#64748b";
  return (
    <span
      className="badge-outline"
      style={{ color, backgroundColor: `${color}22`, border: `1px solid ${color}` }}
    >
      {level}
    </span>
  );
}
