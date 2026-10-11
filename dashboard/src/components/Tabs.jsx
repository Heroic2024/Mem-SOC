import { useState } from "react";

export default function Tabs({ tabs }) {
  const [active, setActive] = useState(0);

  return (
    <div>
      <div className="tab-bar">
        {tabs.map((tab, i) => (
          <button
            key={tab.label}
            className={`tab-button ${i === active ? "active" : ""}`}
            onClick={() => setActive(i)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div>{tabs[active].content}</div>
    </div>
  );
}
