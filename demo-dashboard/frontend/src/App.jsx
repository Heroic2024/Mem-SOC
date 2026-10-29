import { useState } from "react";
import Overview from "./sections/Overview.jsx";
import CorrectlyCaught from "./sections/CorrectlyCaught.jsx";
import PerModelResults from "./sections/PerModelResults.jsx";
import CrossModel from "./sections/CrossModel.jsx";
import Mechanism from "./sections/Mechanism.jsx";
import StatisticalRigor from "./sections/StatisticalRigor.jsx";
import Architecture from "./sections/Architecture.jsx";
import DynamicSection from "./sections/DynamicSection.jsx";

const SECTIONS = [
  { id: "overview", n: "01", label: "Overview", Comp: Overview },
  { id: "caught", n: "02", label: "Correctly Caught", Comp: CorrectlyCaught },
  { id: "per-model", n: "03", label: "Per-Model Results", Comp: PerModelResults },
  { id: "cross-model", n: "04", label: "Cross-Model", Comp: CrossModel },
  { id: "mechanism", n: "05", label: "The Mechanism", Comp: Mechanism },
  { id: "rigor", n: "06", label: "Statistical Rigor", Comp: StatisticalRigor },
  { id: "architecture", n: "07", label: "Architecture", Comp: Architecture },
];

export default function App() {
  const [active, setActive] = useState("overview");

  const current = SECTIONS.find((s) => s.id === active);
  const ActiveComp = current ? current.Comp : DynamicSection;

  return (
    <div className="shell">
      <aside className="rail">
        <div className="rail-brand">MemSOC</div>
        <div className="rail-sub">Final demonstration</div>
        <nav>
          {SECTIONS.map((s) => (
            <button key={s.id} className={active === s.id ? "on" : ""} onClick={() => setActive(s.id)}>
              <span className="n">{s.n}</span> {s.label}
            </button>
          ))}
          <div className="divider" />
          <button className={active === "dynamic" ? "on" : ""} onClick={() => setActive("dynamic")}>
            <span className="n">08</span> Live Demo <span className="tag-live">live</span>
          </button>
        </nav>
      </aside>
      <main>{active === "dynamic" ? <DynamicSection /> : <ActiveComp />}</main>
    </div>
  );
}
