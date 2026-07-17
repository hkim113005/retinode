// The live field canvas: the Ve heatmap with electrode outlines and cell markers —
// the signature canvas from docs/phase-7-design.md. The drawing itself lives in
// chart/plots/field.ts as a pure Scene builder; this component only measures the
// box, paints, and hangs the export menu off it (P7 S7).
import { useEffect, useRef, useState } from "react";
import type { CompareResponse } from "../api/client";
import { sampleGrid } from "../chart/contours";
import { fieldScene } from "../chart/plots/field";
import { drawScene } from "../chart/render";
import { livePalette } from "../chart/scene";
import { FigureExport } from "./FigureExport";

type Probe = { x: number; y: number; ve: number };

export function FieldCanvas({
  data,
  tier = "analytical",
}: {
  data: CompareResponse | null;
  tier?: "analytical" | "fem";
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [probe, setProbe] = useState<Probe | null>(null);
  const inked = tier === "fem"; // FEM results draw crisper (docs/phase-7-design.md)

  // hover to read the actual value under the cursor: colour carries the gestalt,
  // this carries the number (docs/phase-7-design.md)
  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = ref.current;
    if (!canvas || !data) return;
    const { xs_um, ys_um, ve_mV } = data.field;
    const extent = xs_um[xs_um.length - 1] || 1;
    const box = canvas.getBoundingClientRect();
    const x = ((e.clientX - box.left) / box.width) * 2 * extent - extent;
    const y = extent - ((e.clientY - box.top) / box.height) * 2 * extent;
    const ve = sampleGrid(xs_um, ys_um, ve_mV, x, y);
    setProbe(ve == null ? null : { x, y, ve });
  };

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !data) return;
    const size = canvas.getBoundingClientRect().width || 520;
    const scene = fieldScene({ data, size, palette: livePalette(), inked });
    drawScene(canvas, scene, Math.min(window.devicePixelRatio || 1, 2));
  }, [data, inked]);

  return (
    <div className={`card canvas-wrap${inked ? " inked" : ""}`}>
      {probe && (
        <div className="probe" aria-live="off">
          <span className="v">{probe.ve.toFixed(2)}</span> mV
          <span className="at">
            at {probe.x.toFixed(0)}, {probe.y.toFixed(0)} µm
          </span>
        </div>
      )}
      <canvas
        ref={ref}
        className="field"
        style={{ aspectRatio: "1 / 1" }}
        onMouseMove={onMove}
        onMouseLeave={() => setProbe(null)}
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
        <div className="canvas-tools">
          <FigureExport
            name={`field-${tier}`}
            build={({ palette, background }) =>
              data
                ? fieldScene({
                    data,
                    // a fixed generous size: the figure should not inherit whatever
                    // width this browser window happens to have
                    size: 720,
                    palette,
                    inked,
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
