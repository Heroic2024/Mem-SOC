export default function Panel({ title, caption, children }) {
  return (
    <div className="panel">
      <div className="panel-title">{title}</div>
      {caption && <div className="panel-caption">{caption}</div>}
      {children}
    </div>
  );
}
