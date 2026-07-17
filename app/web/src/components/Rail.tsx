// The left rail: the pipeline is the navigation, doubling as a progress indicator,
// with always-on tier + safety badges (docs/phase-7-design.md).
const DESIGN = ["Patch", "Array", "Tissue", "Stimulus", "Results"];
const ANALYSE = ["Compare", "Study", "Validation", "Candidates"];

export function Rail({ active, tier, safe }: { active: string; tier: string; safe: string }) {
  const step = (name: string) => (
    <div key={name} className={`step${name === active ? " active" : " done"}`}>
      <span className="dot" />
      {name}
    </div>
  );
  return (
    <aside className="rail">
      <div className="card brand">
        <div className="wordmark">Retinode</div>
        <div className="sub">Electrode studio</div>
      </div>
      <nav className="card nav">
        <div className="grp">Design</div>
        {DESIGN.map(step)}
        <div className="grp">Analyse</div>
        {ANALYSE.map(step)}
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
