// The left rail: the pipeline is the navigation, doubling as a progress indicator,
// with always-on tier + safety badges (docs/phase-7-design.md). The Analyse screens
// that are built (Compare, Study) are clickable; the rest are shown but inert.
import type { Screen } from "../nav";

const DESIGN = ["Patch", "Array", "Tissue", "Stimulus", "Results"];
const ANALYSE = ["Compare", "Study", "Validation", "Candidates"];
const NAVIGABLE = new Set<string>(["Compare", "Study"]);

export function Rail({
  active,
  tier,
  safe,
  onNavigate,
}: {
  active: string;
  tier: string;
  safe: string;
  onNavigate?: (screen: Screen) => void;
}) {
  const step = (name: string, done: boolean) => {
    const cls = `step${name === active ? " active" : done ? " done" : ""}`;
    const clickable = onNavigate && NAVIGABLE.has(name) && name !== active;
    return clickable ? (
      <button key={name} className={cls} onClick={() => onNavigate(name as Screen)}>
        <span className="dot" />
        {name}
      </button>
    ) : (
      <div key={name} className={cls}>
        <span className="dot" />
        {name}
      </div>
    );
  };
  return (
    <aside className="rail">
      <div className="card brand">
        <div className="wordmark">Retinode</div>
        <div className="sub">Electrode studio</div>
      </div>
      <nav className="card nav">
        <div className="grp">Design</div>
        {DESIGN.map((n) => step(n, true))}
        <div className="grp">Analyse</div>
        {ANALYSE.map((n) => step(n, false))}
      </nav>
      <div className="card badges">
        <div className="badge tier">
          <span className="k">Accuracy</span>
          <span className="v">{tier}</span>
        </div>
        <div className="badge safe">
          <span className="k">Safety</span>
          <span className="v">{safe}</span>
        </div>
      </div>
    </aside>
  );
}
