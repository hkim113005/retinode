// The export affordance that hangs on every workhorse plot (P7 S7 / D8). It rebuilds
// the plot's Scene at export time from the same builder the screen uses, so the file
// is the figure, not a lookalike.
//
// The default is the PAPER palette, not the live theme: a dark-mode PNG is unusable
// in a manuscript. "Screen colours" is there for slides and for pasting back into
// this app's own docs.
import { useState } from "react";
import { exportPng, exportSvg } from "../chart/export";
import type { Palette, Scene } from "../chart/scene";
import { PAPER, livePalette } from "../chart/scene";

export type SceneBuilder = (opts: { palette: Palette; background: boolean }) => Scene | null;

export function FigureExport({ name, build }: { name: string; build: SceneBuilder }) {
  const [paper, setPaper] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const run = (fmt: "svg" | "png") => {
    setError(null);
    const scene = build({ palette: paper ? PAPER : livePalette(), background: true });
    if (!scene) return setError("nothing to export yet");
    try {
      if (fmt === "svg") exportSvg(scene, `retinode-${name}.svg`);
      else void exportPng(scene, `retinode-${name}.png`, 3).catch((e: unknown) => setError(msg(e)));
    } catch (e: unknown) {
      setError(msg(e));
    }
  };

  return (
    <details className="figexp">
      <summary aria-label="Export this figure">Export ▾</summary>
      <div className="figexp-menu">
        <div className="figexp-seg" role="group" aria-label="Figure colours">
          <button className={paper ? "on" : ""} onClick={() => setPaper(true)}>
            Paper
          </button>
          <button className={paper ? "" : "on"} onClick={() => setPaper(false)}>
            Screen
          </button>
        </div>
        <button className="figexp-go" onClick={() => run("svg")}>
          SVG <span>vector · editable</span>
        </button>
        <button className="figexp-go" onClick={() => run("png")}>
          PNG <span>3× · ~300 dpi</span>
        </button>
        {error && (
          <p className="figexp-err" role="alert">
            {error}
          </p>
        )}
      </div>
    </details>
  );
}

const msg = (e: unknown) => (e instanceof Error ? e.message : "export failed");
