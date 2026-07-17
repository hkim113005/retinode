// The activation-vs-amplitude plot, with the button that earns it. The sweep is a
// background job (~24 amplitudes × the population ≈ one scorecard's worth of NEURON),
// so this owns its own submit-and-poll rather than riding the scorecard's.
import { useEffect, useRef } from "react";
import type { AmplitudeSweep, Scorecard } from "../api/client";
import { activationHeight, activationScene } from "../chart/plots/activation";
import { drawScene } from "../chart/render";
import { livePalette } from "../chart/scene";
import type { Progress } from "../screens/Compare";
import { FigureExport } from "./FigureExport";

export function ActivationPlot({
  data,
  scorecard,
  progress,
  cached,
  onRun,
}: {
  data: AmplitudeSweep | null | undefined;
  scorecard: Scorecard | null | undefined;
  progress: Progress | null;
  cached: boolean;
  onRun: () => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const height = data ? activationHeight(data) : 0;
  const threshold = scorecard?.activated ? scorecard.target_uA : null;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !data) return;
    const w = canvas.getBoundingClientRect().width || 520;
    const scene = activationScene({
      data,
      width: w,
      palette: livePalette(),
      targetThreshold_uA: threshold,
    });
    drawScene(canvas, scene, Math.min(window.devicePixelRatio || 1, 2));
  }, [data, threshold]);

  if (progress) {
    return (
      <div className="card panel">
        <h2>Activation vs amplitude</h2>
        <p className="empty">{progress.message}…</p>
        <div className="progress" aria-label="sweep progress">
          <span style={{ width: `${Math.round(progress.fraction * 100)}%` }} />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card panel">
        <h2>Activation vs amplitude</h2>
        <p className="empty">
          The threshold search probes a ladder of amplitudes and keeps only the crossing.
          Sweep a stated grid instead to see the whole picture — who joins next, and
          whether anything stops firing again as current rises.
        </p>
        <button className="btn" onClick={onRun}>
          Sweep amplitudes
        </button>
      </div>
    );
  }

  const blockers = data.curves.filter((c) => c.blocks);
  return (
    <div className="card canvas-wrap">
      <canvas
        ref={ref}
        className="field"
        style={{ height, width: "100%" }}
        aria-label="Activation of each cell versus stimulus amplitude"
      />
      <div className="legend">
        <span>
          <span className="sw" style={{ background: "var(--field)" }} />
          <b>target</b>
        </span>
        <span>step up = fires</span>
        {blockers.length > 0 && (
          <span className="warn">
            ⚠ {blockers.map((c) => c.cell_id).join(", ")} stops firing at high current
          </span>
        )}
        {cached && <span className="pill cached">cached</span>}
        <div className="canvas-tools">
          <FigureExport
            name="activation"
            build={({ palette, background }) =>
              activationScene({
                data,
                width: 720,
                palette,
                targetThreshold_uA: threshold,
                background,
              })
            }
          />
        </div>
      </div>
    </div>
  );
}
