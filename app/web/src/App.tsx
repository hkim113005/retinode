import { useState } from "react";
import type { Screen } from "./nav";
import { Compare } from "./screens/Compare";
import { Study } from "./screens/Study";

export function App() {
  const [screen, setScreen] = useState<Screen>("Compare");
  return screen === "Study" ? (
    <Study onNavigate={setScreen} />
  ) : (
    <Compare onNavigate={setScreen} />
  );
}
