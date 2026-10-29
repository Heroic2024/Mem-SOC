export default function Histogram({ labels, counts }) {
  const max = Math.max(...counts, 1);
  return (
    <>
      <div className="hist">
        {counts.map((c, i) => (
          <div
            key={labels[i]}
            className={`col ${c === max ? "peak" : ""}`}
            style={{ height: `${Math.max(2, (c / max) * 100)}%` }}
            title={`${labels[i]}: ${c}`}
          />
        ))}
      </div>
      <div className="hist-labels">
        {labels.map((l) => (
          <span key={l}>{l}</span>
        ))}
      </div>
    </>
  );
}
