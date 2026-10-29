const COLORS = ["var(--color-good)", "var(--color-accent)", "var(--color-warn)", "var(--color-text-faint)", "var(--color-bad)"];

export default function Donut({ data }) {
  // data: [{label, value}], sorted desc
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  let offset = 0;
  const segments = data.map((d, i) => {
    const frac = (d.value / total) * 100;
    const seg = { ...d, color: COLORS[i % COLORS.length], dash: `${frac} ${100 - frac}`, dashoffset: -offset };
    offset += frac;
    return seg;
  });

  return (
    <div className="donut-wrap">
      <svg width="120" height="120" viewBox="0 0 42 42">
        <circle cx="21" cy="21" r="15.9" fill="transparent" stroke="var(--color-border)" strokeWidth="6" />
        {segments.map((s) => (
          <circle
            key={s.label}
            cx="21"
            cy="21"
            r="15.9"
            fill="transparent"
            stroke={s.color}
            strokeWidth="6"
            strokeDasharray={s.dash}
            strokeDashoffset={s.dashoffset + 25}
          />
        ))}
      </svg>
      <div className="donut-legend">
        {segments.map((s) => (
          <div className="row" key={s.label}>
            <span className="sw" style={{ background: s.color }} />
            {s.label}
            <span className="amt">{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
