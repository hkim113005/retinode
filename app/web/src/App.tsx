import { useState } from "react";
import type { StudyPoint } from "./api/client";
import type { Screen } from "./nav";
import { Candidates } from "./screens/Candidates";
import { Compare } from "./screens/Compare";
import { Study } from "./screens/Study";
import { Validation } from "./screens/Validation";

export function App() {
  const [screen, setScreen] = useState<Screen>("Compare");
  // the sweep's results live here so Study's frontier carries to Candidates
  const [studyPoints, setStudyPoints] = useState<StudyPoint[]>([]);
  // a brushed subset of that sweep, when the user narrowed it on the Pareto (S7c).
  // null means "no narrowing" — Candidates ranks the whole sweep.
  const [focus, setFocus] = useState<StudyPoint[] | null>(null);

  if (screen === "Study")
    return (
      <Study
        onNavigate={setScreen}
        onPoints={(p) => {
          setStudyPoints(p);
          setFocus(null); // a fresh sweep retires the old brush
        }}
        onFocus={setFocus}
        points={studyPoints}
      />
    );
  if (screen === "Validation") return <Validation onNavigate={setScreen} />;
  if (screen === "Candidates")
    return (
      <Candidates
        onNavigate={setScreen}
        points={focus ?? studyPoints}
        brushed={focus != null}
        onClearBrush={() => setFocus(null)}
      />
    );
  return <Compare onNavigate={setScreen} />;
}
