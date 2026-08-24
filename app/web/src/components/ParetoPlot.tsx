// The selectivity-versus-cost decision surface. The drawing lives in
// chart/plots/pareto.ts as a pure Scene builder; this component measures, paints,
// hit-tests against the same geometry the scene used, and carries the two
// interactions that make the frontier explorable: hover a design to read its
// numbers, drag a box to shortlist a set (P7 S7c).
import { useEffect, useRef, useState } from "react";
import type { StudyPoint } from "../api/client";
import { paretoGeom, paretoScene } from "../chart/plots/pareto";
import { drawScene } from "../chart/render";
import { useResizeRedraw } from "../chart/useResizeRedraw";
import { livePalette } from "../chart/scene";
import { FigureExport } from "./FigureExport";

const RATIO = 0.6; // height / width, keeping the frontier readable rather than squat
const HIT = 20; // px: these marks are small, so be generous
const DRAG = 4; // px before a click becomes a brush

type Box = { x0: number; y0: number; x1: number; y1: number };
type Hover = { p: StudyPoint; x: number; y: number };

const norm = (b: Box) => ({
  l: Math.min(b.x0, b.x1),
  r: Math.max(b.x0, b.x1),
  t: Math.min(b.y0, b.y1),
  b: Math.max(b.y0, b.y1),
});

export function ParetoPlot({
  points,
  selected,
  onSelect,
  onBrush,
}: {
  points: StudyPoint[];
  selected: StudyPoint | null;
  onSelect: (p: StudyPoint) => void;
  onBrush?: (p: StudyPoint[]) => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const rtick = useResizeRedraw(ref);
  const [box, setBox] = useState<Box | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const dragging = useRef(false);

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
      brush: box && dragging.current ? norm(box) : null,
    });
    drawScene(canvas, scene, Math.min(window.devicePixelRatio || 1, 2));
  }, [points, selected, box, rtick]);

  // measure at event time rather than trusting state: after a window resize a
  // stored width is stale and every hit test would land off the marks
  const local = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top, w: r.width };
  };

  const nearest = (mx: number, my: number, w: number): StudyPoint | null => {
    const g = paretoGeom(points, w, w * RATIO);
    if (!g) return null;
    let best: StudyPoint | null = null;
    let bd = HIT;
    for (const p of points) {
      const d = Math.hypot(g.x(p) - mx, g.y(p) - my);
      if (d < bd) {
        bd = d;
        best = p;
      }
    }
    return best;
  };

  const onDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = local(e);
    dragging.current = false;
    setBox({ x0: x, y0: y, x1: x, y1: y });
  };

  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y, w } = local(e);
    if (box) {
      // a small wobble is still a click; past DRAG it becomes a brush
      if (!dragging.current && Math.hypot(x - box.x0, y - box.y0) > DRAG) dragging.current = true;
      setBox({ ...box, x1: x, y1: y });
      if (dragging.current) return setHover(null);
    }
    const p = nearest(x, y, w);
    setHover(p ? { p, x, y } : null);
  };

  const onUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y, w } = local(e);
    const wasDrag = dragging.current;
    const b = box;
    dragging.current = false;
    setBox(null);
    if (!wasDrag || !b) {
      const p = nearest(x, y, w);
      if (p) onSelect(p);
      return;
    }
    const g = paretoGeom(points, w, w * RATIO);
    if (!g) return;
    const n = norm({ ...b, x1: x, y1: y });
    // brush the safe designs only: an unsafe one is not a candidate for anything
    const inside = points.filter(
      (p) => p.safe && g.x(p) >= n.l && g.x(p) <= n.r && g.y(p) >= n.t && g.y(p) <= n.b,
    );
    if (inside.length) onBrush?.(inside);
  };

  const leave = () => {
    dragging.current = false;
    setBox(null);
    setHover(null);
  };

  return (
    <div className="card canvas-wrap">
      {hover && (
        <div
          className="tip"
          style={{ left: hover.x + 14, top: hover.y + 10 }}
          role="tooltip"
          aria-live="off"
        >
          <b>
            d{hover.p.diameter_um} · pitch {hover.p.pitch_um} µm
          </b>
          <span>
            <i>{hover.p.cost_uA.toFixed(1)}</i> µA to fire
          </span>
          <span>
            <i>{hover.p.selectivity_uA.toFixed(1)}</i> µA window
          </span>
          <span className={hover.p.safe ? "ok" : "bad"}>
            {hover.p.safe ? "charge-safe" : "over the charge limit"}
          </span>
        </div>
      )}
      <canvas
        ref={ref}
        className="field"
        style={{ aspectRatio: "5 / 3", cursor: "crosshair" }}
        onMouseDown={onDown}
        onMouseMove={onMove}
        onMouseUp={onUp}
        onMouseLeave={leave}
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
        <span className="hint">drag a box to shortlist</span>
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
