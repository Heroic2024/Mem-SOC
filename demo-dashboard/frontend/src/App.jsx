import { useState } from "react";
import StaticSection from "./sections/StaticSection.jsx";
import DynamicSection from "./sections/DynamicSection.jsx";

export default function App() {
  const [tab, setTab] = useState("static");

  return (
    <div className="app">
      <div className="app-header">
        <div>
          <h1>MemSOC — Does Persistent Memory Help an LLM Triage SOC Alerts?</h1>
          <div className="subtitle">Final demonstration dashboard</div>
        </div>
      </div>

      <div className="top-tabs">
        <button className={tab === "static" ? "active" : ""} onClick={() => setTab("static")}>
          Static — Findings
        </button>
        <button className={tab === "dynamic" ? "active" : ""} onClick={() => setTab("dynamic")}>
          Dynamic — Live Demo
        </button>
      </div>

      {tab === "static" ? <StaticSection /> : <DynamicSection />}
    </div>
  );
}
