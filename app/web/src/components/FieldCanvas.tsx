// The live field canvas: the Ve heatmap with electrode outlines and cell markers —
// the signature canvas from docs/phase-7-design.md. The drawing itself lives in
// chart/plots/field.ts as a pure Scene builder; this component only measures the
// box, paints, and hangs the export menu off it (P7 S7).
import { useEffect, useRef } from "react";
import type { CompareResponse } from "../api/client";
import { fieldScene } from "../chart/plots/field";
import { drawScene } from "../chart/render";
import { livePalette } from "../chart/scene";
import { FigureExport } from "./FigureExport";

export function FieldCanvas({
  data,
  tier = "analytical",
}: {
  data: CompareResponse | null;
  tier?: "analytical" | "fem";
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const inked = tier === "fem"; // FEM results draw crisper (docs/phase-7-design.md)

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !data) return;
    const size = canvas.getBoundingClientRect().width || 520;
    const scene = fieldScene({ data, size, palette: livePalette(), inked });
    drawScene(canvas, scene, Math.min(window.devicePixelRatio || 1, 2));
  }, [data, inked]);

  return (
    <div className={`card canvas-wrap${inked ? " inked" : ""}`}>
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
