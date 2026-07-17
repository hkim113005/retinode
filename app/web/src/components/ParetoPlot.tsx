// The selectivity-versus-cost decision surface (docs/phase-7-design.md): dominated
// designs recede, the frontier is a lit curve, unsafe designs are hollow-red and
// excluded, the selected point is ringed. Click a point to inspect it.
import { useEffect, useRef } from "react";
import type { StudyPoint } from "../api/client";

function cssVar(n: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(n).trim();
}
function withAlpha(hex: string, a: number): string {
  const h = hex.replace("#", "");
  const f = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(f || "808080", 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

const PAD = { l: 56, r: 16, t: 18, b: 40 };

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
  const geom = useRef<{ x: (p: StudyPoint) => number; y: (p: StudyPoint) => number } | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = canvas.getContext("2d");
    } catch {
      return;
    }
    if (!ctx) return;

    const box = canvas.getBoundingClientRect();
    const W = box.width || 640;
    const H = W * 0.6;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    const ink = cssVar("--canvas-ink");
    const muted = cssVar("--muted");
    const accent = cssVar("--field");
    const warm = cssVar("--warm");
    const alert = cssVar("--alert");
    const mono = cssVar("--mono") || "monospace";

    if (points.length === 0) {
      ctx.fillStyle = withAlpha(muted, 0.7);
      ctx.font = `13px ${cssVar("--sans")}`;
      ctx.textAlign = "center";
      ctx.fillText("Run the study to fill the frontier", W / 2, H / 2);
      geom.current = null;
      return;
    }

    const costs = points.map((p) => p.cost_uA);
    const sels = points.map((p) => p.selectivity_uA);
    const x0 = Math.min(...costs) - 1;
    const x1 = Math.max(...costs) + 1;
    const y0 = 0;
    const y1 = Math.max(...sels) + 1;
    const x = (p: StudyPoint) => PAD.l + ((p.cost_uA - x0) / (x1 - x0)) * (W - PAD.l - PAD.r);
    const y = (p: StudyPoint) => PAD.t + (1 - (p.selectivity_uA - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
    geom.current = { x, y };

    // grid + axes
    ctx.strokeStyle = withAlpha(muted, 0.1);
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const gx = PAD.l + ((W - PAD.l - PAD.r) * i) / 4;
      const gy = PAD.t + ((H - PAD.t - PAD.b) * i) / 4;
      ctx.beginPath();
      ctx.moveTo(gx, PAD.t);
      ctx.lineTo(gx, H - PAD.b);
      ctx.moveTo(PAD.l, gy);
      ctx.lineTo(W - PAD.r, gy);
      ctx.stroke();
    }
    ctx.fillStyle = withAlpha(muted, 0.95);
    ctx.font = `11px ${cssVar("--sans")}`;
    ctx.textAlign = "center";
    ctx.fillText("µA to fire the target  →  more current", W / 2, H - 12);
    ctx.save();
    ctx.translate(15, H / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("selective window (µA)  →  more selective", 0, 0);
    ctx.restore();
    ctx.fillStyle = withAlpha(accent, 0.6);
    ctx.font = `10px ${mono}`;
    ctx.textAlign = "left";
    ctx.fillText("◤ better", PAD.l + 6, PAD.t + 13);

    // frontier line (safe + on_frontier, sorted by cost)
    const front = points.filter((p) => p.on_frontier && p.safe).sort((a, b) => a.cost_uA - b.cost_uA);
    if (front.length > 1) {
      ctx.strokeStyle = withAlpha(accent, 0.55);
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      front.forEach((p, i) => (i ? ctx!.lineTo(x(p), y(p)) : ctx!.moveTo(x(p), y(p))));
      ctx.stroke();
    }

    // points
    for (const p of points) {
      const px = x(p);
      const py = y(p);
      const isSel = selected != null && p.diameter_um === selected.diameter_um && p.pitch_um === selected.pitch_um;
      if (!p.safe) {
        ctx.strokeStyle = withAlpha(alert, 0.75);
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.arc(px, py, 4, 0, Math.PI * 2);
        ctx.stroke();
        continue;
      }
      const r = p.on_frontier ? 5.5 : 3.6;
      if (isSel) {
        ctx.fillStyle = withAlpha(warm, 0.2);
        ctx.beginPath();
        ctx.arc(px, py, r + 5, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = isSel ? warm : p.on_frontier ? accent : withAlpha(ink, 0.3);
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fill();
    }
  }, [points, selected]);

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const g = geom.current;
    const canvas = ref.current;
    if (!g || !canvas || points.length === 0) return;
    const box = canvas.getBoundingClientRect();
    const mx = ((e.clientX - box.left) / box.width) * (box.width || 640);
    const my = ((e.clientY - box.top) / box.height) * (box.width || 640) * 0.6;
    let best: StudyPoint | null = null;
    let bd = 20;
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
      </div>
    </div>
  );
}
