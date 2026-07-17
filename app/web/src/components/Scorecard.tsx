// The operating-window scorecard. It needs a threshold search (NEURON), so it's not
// live — the user runs it. S3 turns that into a streamed job; for now it's a request.
import type { Scorecard as ScorecardData } from "../api/client";

function uA(x: number | null | undefined): string {
  return x == null ? "—" : `${x.toFixed(1)} µA`;
}

export function Scorecard({
  data,
  loading,
  onRun,
}: {
  data: ScorecardData | null | undefined;
  loading: boolean;
  onRun: () => void;
}) {
  return (
    <div className="card panel">
      <h2>Scorecard</h2>
      {data == null ? (
        <>
          <p className="empty">
            The operating window comes from a threshold search on the cell population.
            Run it to score this configuration.
          </p>
          <button className="btn" onClick={onRun} disabled={loading}>
            {loading ? "Scoring…" : "Run scorecard"}
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
          </div>
          <div className="sub">selective window above the target threshold</div>
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
        </>
      )}
    </div>
  );
}
