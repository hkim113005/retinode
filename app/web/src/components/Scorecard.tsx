// The operating-window scorecard. It needs a threshold search (NEURON), so it runs
// as a background job: while `progress` is set, the panel shows the job's progress;
// when done, the operating window renders (with a "cached" note if it was reused).
import type { Scorecard as ScorecardData } from "../api/client";
import type { Progress } from "../screens/Compare";

// An unbounded window is a real evaluator state (limiting: "none"), so infinities
// have to read as ∞ — `toFixed` would print the literal "Infinity µA".
function uA(x: number | null | undefined): string {
  if (x == null) return "—";
  return Number.isFinite(x) ? `${x.toFixed(1)} µA` : "∞";
}

function ratio(x: number | null | undefined): string {
  if (x == null) return "—";
  return Number.isFinite(x) ? `${x.toFixed(2)}×` : "∞×";
}

// What closed the window — the difference between "a bystander fires" and "the
// charge limit bites" is the whole design decision, so it is spelled out.
const LIMITING: Record<string, string> = {
  off_target: "a bystander fires",
  safety: "the charge limit",
  none: "nothing — unbounded",
};

export function Scorecard({
  data,
  progress,
  cached,
  onRun,
}: {
  data: ScorecardData | null | undefined;
  progress: Progress | null;
  cached: boolean;
  onRun: () => void;
}) {
  const running = progress != null;
  return (
    <div className="card panel">
      <h2>Scorecard</h2>

      {running ? (
        <>
          <p className="empty">{progress.message}…</p>
          <div className="progress" aria-label="scoring progress">
            <span style={{ width: `${Math.round(progress.fraction * 100)}%` }} />
          </div>
        </>
      ) : data == null ? (
        <>
          <p className="empty">
            The operating window comes from a threshold search on the cell population.
            Run it to score this configuration.
          </p>
          <button className="btn" onClick={onRun}>
            Run scorecard
          </button>
        </>
      ) : !data.activated ? (
        <p className="empty">The target never fired in the searched range — no operating window.</p>
      ) : (
        <>
          <div className="verdict">
            <span className="big">{uA(data.usable_margin_uA)}</span>
            <span className={`pill ${data.usable ? "win" : "lost"}`}>
              {data.usable ? "usable" : "tight"}
            </span>
            {cached && <span className="pill cached">cached</span>}
          </div>
          <div className="sub">
            selective window above the target threshold
            {data.limiting && (
              <>
                {" · limited by "}
                <b>{LIMITING[data.limiting] ?? data.limiting}</b>
              </>
            )}
          </div>
          <div className="rows">
            <div className="row">
              <span className="k">Target threshold</span>
              <span className="v warm">{uA(data.target_uA)}</span>
            </div>
            <div className="row">
              <span className="k">First off-target</span>
              <span className="v">{uA(data.off_min_uA)}</span>
            </div>
            <div className="row">
              <span className="k">Selectivity</span>
              <span className="v ok">{ratio(data.ratio)}</span>
            </div>
            <div className="row">
              <span className="k">Selective window</span>
              <span className="v ok">
                {uA(data.window_lo_uA)} – {uA(data.window_hi_uA)}
              </span>
            </div>
            <div className="row">
              <span className="k">Safety ceiling</span>
              <span className={`v ${data.safe_at_target ? "ok" : "alert"}`}>
                {uA(data.safety_ceiling_uA)}
              </span>
            </div>
          </div>
          <button className="btn ghost" onClick={onRun}>
            Re-run
          </button>
        </>
      )}
    </div>
  );
}
