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

  if (screen === "Study")
    return <Study onNavigate={setScreen} onPoints={setStudyPoints} points={studyPoints} />;
  if (screen === "Validation") return <Validation onNavigate={setScreen} />;
  if (screen === "Candidates") return <Candidates onNavigate={setScreen} points={studyPoints} />;
  return <Compare onNavigate={setScreen} />;
}
