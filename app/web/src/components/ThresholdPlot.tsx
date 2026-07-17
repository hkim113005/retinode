// The threshold plot: renders the scorecard's per-cell thresholds on a current axis.
// Like the other plots this is a thin shell over a pure Scene builder, so it exports
// as a figure for free.
import { useEffect, useRef } from "react";
import type { Scorecard } from "../api/client";
import { thresholdHeight, thresholdRows, thresholdScene } from "../chart/plots/thresholds";
import { drawScene } from "../chart/render";
import { livePalette } from "../chart/scene";
import { FigureExport } from "./FigureExport";

export function ThresholdPlot({ data }: { data: Scorecard | null | undefined }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const height = data ? thresholdHeight(data) : 0;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !data) return;
    const w = canvas.getBoundingClientRect().width || 520;
    const scene = thresholdScene({ data, width: w, palette: livePalette() });
    drawScene(canvas, scene, Math.min(window.devicePixelRatio || 1, 2));
  }, [data]);

  // nothing to say before a scorecard exists — the Scorecard panel already prompts
  if (!data || !thresholdRows(data).length) return null;

  return (
    <div className="card canvas-wrap">
      <canvas
        ref={ref}
        className="field"
        style={{ height, width: "100%" }}
        aria-label="Threshold of each cell in µA, with the selective window and charge limit"
      />
      <div className="legend">
        <span>
          <span className="sw" style={{ background: "var(--field)" }} />
          <b>target</b>
        </span>
        <span>
          <span className="sw" style={{ background: "var(--warm)" }} />
          binds the window
        </span>
        <span>
          <span className="sw" style={{ background: "var(--alert)" }} />
          charge limit
        </span>
        <div className="canvas-tools">
          <FigureExport
            name="thresholds"
            build={({ palette, background }) =>
              thresholdScene({ data, width: 640, palette, background })
            }
          />
        </div>
      </div>
    </div>
  );
}
