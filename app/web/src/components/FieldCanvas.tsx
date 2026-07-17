// The live field canvas: the Ve heatmap (diverging, blue negative / warm positive,
// centred on zero) with electrode outlines and cell markers overlaid — the signature
// canvas from docs/phase-7-design.md, on the analytical tier.
import { useEffect, useRef } from "react";
import type { CompareResponse } from "../api/client";

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function withAlpha(hex: string, a: number): string {
  const h = hex.replace("#", "");
  const f = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(f || "808080", 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

export function FieldCanvas({ data }: { data: CompareResponse | null }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !data) return;
    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = canvas.getContext("2d"); // jsdom throws (no canvas support) — nothing to paint
    } catch {
      return;
    }
    if (!ctx) return;

    const box = canvas.getBoundingClientRect();
    const size = box.width || 520;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);

    const { xs_um, ys_um, ve_mV, vmax_mV } = data.field;
    const extent = xs_um[xs_um.length - 1] || 1;
    const toX = (x: number) => ((x + extent) / (2 * extent)) * size;
    const toY = (y: number) => ((extent - y) / (2 * extent)) * size;
    const field = cssVar("--field");
    const warm = cssVar("--warm");
    const ink = cssVar("--canvas-ink");

    // diverging heatmap: alpha ∝ |Ve| / vmax, blue for negative, warm for positive
    const n = xs_um.length;
    const dx = (size / n) * 1.06;
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const t = ve_mV[i][j] / (vmax_mV || 1);
        const a = Math.min(1, Math.abs(t));
        if (a < 0.02) continue;
        ctx.fillStyle = withAlpha(t < 0 ? field : warm, a * 0.85);
        ctx.fillRect(toX(xs_um[j]) - dx / 2, toY(ys_um[i]) - dx / 2, dx, dx);
      }
    }

    // electrodes
    for (const e of data.electrodes) {
      const r = Math.max(3, (e.radius_um / (2 * extent)) * size);
      ctx.beginPath();
      ctx.arc(toX(e.x_um), toY(e.y_um), r, 0, Math.PI * 2);
      ctx.fillStyle = withAlpha(ink, 0.14);
      ctx.fill();
      ctx.strokeStyle = withAlpha(ink, 0.6);
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    // cells: target filled accent, off-target hollow
    for (const c of data.cells) {
      ctx.beginPath();
      ctx.arc(toX(c.x_um), toY(c.y_um), c.is_target ? 6 : 5, 0, Math.PI * 2);
      if (c.is_target) {
        ctx.fillStyle = field;
        ctx.fill();
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      } else {
        ctx.fillStyle = "rgba(0,0,0,0)";
        ctx.fill();
        ctx.strokeStyle = withAlpha(ink, 0.6);
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    }
  }, [data]);

  return (
    <div className="card canvas-wrap">
      <canvas
        ref={ref}
        className="field"
        style={{ aspectRatio: "1 / 1" }}
        aria-label="Extracellular potential field with electrode outlines and cell markers"
      />
      <div className="legend">
        <span>
          <span className="sw" style={{ background: "var(--field)" }} />
          <b>Ve</b> potential
        </span>
        <span>
          <span className="sw" style={{ background: "var(--accent)" }} />
          <b>target</b> cell
        </span>
        <span>hollow = off-target · ring = electrode</span>
      </div>
    </div>
  );
}
