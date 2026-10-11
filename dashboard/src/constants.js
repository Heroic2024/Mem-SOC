// Shared visual constants -- kept in one place so every chart, badge,
// and table uses the exact same severity color mapping.

export const SEVERITY_ORDER = ["Critical", "High", "Medium", "Low"];

export const SEVERITY_COLORS = {
  Critical: "#ef4444",
  High: "#f97316",
  Medium: "#eab308",
  Low: "#22c55e",
};

export const CONFIDENCE_ORDER = ["<0.5", "0.5-0.7", "0.7-0.9", "0.9-1.0"];

export const ACCENT = "#3b82f6";

export const CHART_THEME = {
  grid: "#26334a",
  axis: "#8b9bb8",
  tick: "#cbd5e1",
  tooltipBg: "#141d2e",
  tooltipBorder: "#263449",
  label: "#e6edf7",
};
