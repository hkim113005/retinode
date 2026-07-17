// Recent runs. Scoring a configuration costs a NEURON threshold search, so a result
// is worth keeping: the strip remembers the last few, shows their windows side by
// side, and restores the whole configuration on click.
//
// This is what makes the screen a *Compare* rather than a viewer — the design doc's
// "Compare is a difference, not two charts". Without it, deciding between two
// geometries means re-running one from memory.
import type { Scorecard as ScorecardData } from "../api/client";
import type { Controls } from "./ControlRail";

export const MAX_RUNS = 6;

export type Run = {
  id: string;
  controls: Controls;
  scorecard: ScorecardData;
};

/** A stable identity for a configuration: same knobs → same run. */
export function runKey(c: Controls): string {
  return [c.layout, c.electrode_um, c.pitch_um, c.phase_width_us, c.neighbor_um, c.sigma_S_per_m].join(
    "/",
  );
}

/** Newest first, de-duplicated by configuration, capped at MAX_RUNS. */
export function remember(runs: Run[], run: Run): Run[] {
  return [run, ...runs.filter((r) => r.id !== run.id)].slice(0, MAX_RUNS);
}

const win = (s: ScorecardData): string => {
  if (!s.activated) return "no window";
  const m = s.usable_margin_uA;
  if (m == null) return "—";
  return Number.isFinite(m) ? `${m.toFixed(1)} µA` : "∞";
};

const ratio = (s: ScorecardData): string => {
  if (s.ratio == null) return "";
  return Number.isFinite(s.ratio) ? `${s.ratio.toFixed(2)}×` : "∞×";
};

export function History({
  runs,
  current,
  onRestore,
}: {
  runs: Run[];
  current: string;
  onRestore: (c: Controls) => void;
}) {
  if (!runs.length) return null;
  return (
    <div className="card runs">
      <div className="runs-head">
        <h2>Recent runs</h2>
        <span className="foot">click to restore that configuration</span>
      </div>
      <div className="runs-strip">
        {runs.map((r) => (
          <button
            key={r.id}
            className={`run${r.id === current ? " on" : ""}`}
            onClick={() => onRestore(r.controls)}
            aria-label={`Restore ${r.controls.electrode_um} µm ${r.controls.layout} run`}
          >
            <span className="w">{win(r.scorecard)}</span>
            <span className="r">{ratio(r.scorecard)}</span>
            <span className="c">
              {r.controls.layout === "bipolar" ? "bipolar" : "monopolar"} · {r.controls.phase_width_us} µs
            </span>
            <span className="c">
              Ø{r.controls.electrode_um} · nbr {r.controls.neighbor_um} · σ{r.controls.sigma_S_per_m}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
