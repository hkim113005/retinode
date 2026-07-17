// The selectivity-versus-cost decision surface. The drawing lives in
// chart/plots/pareto.ts as a pure Scene builder; this component measures, paints,
// hit-tests clicks against the same geometry the scene used, and hangs the export
// menu off the plot (P7 S7).
import { useEffect, useRef } from "react";
import type { StudyPoint } from "../api/client";
import { paretoGeom, paretoScene } from "../chart/plots/pareto";
import { drawScene } from "../chart/render";
import { livePalette } from "../chart/scene";
import { FigureExport } from "./FigureExport";

const RATIO = 0.6; // height / width — keeps the frontier readable, not squat

export function ParetoPlot({
  points,
  selected,
  onSelect,
}: {
  points: StudyPoint[];
  selected: StudyPoint | null;
  onSelect: (p: StudyPoint) => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const w = canvas.getBoundingClientRect().width || 640;
    const scene = paretoScene({
      points,
      selected,
      width: w,
      height: w * RATIO,
      palette: livePalette(),
    });
    drawScene(canvas, scene, Math.min(window.devicePixelRatio || 1, 2));
  }, [points, selected]);

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = ref.current;
    if (!canvas) return;
    // measure at click time rather than trusting state: after a window resize the
    // stored width is stale and every hit test would land off the marks
    const box = canvas.getBoundingClientRect();
    const g = paretoGeom(points, box.width, box.width * RATIO);
    if (!g) return;
    const mx = e.clientX - box.left;
    const my = e.clientY - box.top;
    let best: StudyPoint | null = null;
    let bd = 20; // px — generous, these marks are small
    for (const p of points) {
      const d = Math.hypot(g.x(p) - mx, g.y(p) - my);
      if (d < bd) {
        bd = d;
        best = p;
      }
    }
    if (best) onSelect(best);
  };

  return (
    <div className="card canvas-wrap">
      <canvas
        ref={ref}
        className="field"
        style={{ aspectRatio: "5 / 3", cursor: "crosshair" }}
        onClick={handleClick}
        aria-label="Pareto frontier of electrode geometries: selective window versus current cost"
      />
      <div className="legend">
        <span>
          <span className="sw" style={{ background: "var(--accent)" }} />
          <b>frontier</b>
        </span>
        <span>
          <span className="sw" style={{ background: "var(--faint)" }} />
          dominated
        </span>
        <span>
          <span className="sw" style={{ background: "var(--alert)", borderRadius: "50%" }} />
          over the charge limit
        </span>
        <div className="canvas-tools">
          <FigureExport
            name="pareto"
            build={({ palette, background }) =>
              points.length
                ? paretoScene({
                    points,
                    selected,
                    width: 880,
                    height: 880 * RATIO,
                    palette,
                    background,
                  })
                : null
            }
          />
        </div>
      </div>
    </div>
  );
}
