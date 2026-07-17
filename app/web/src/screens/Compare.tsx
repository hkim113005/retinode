// The Compare screen: control rail → live analytical field, plus an on-demand
// scorecard. Editing a control refetches the field (debounced); the field is fast
// and NEURON-free, so the preview updates as you drag. The scorecard is separate
// state — a field refetch never clobbers a computed operating window, and changing
// a control clears the (now-stale) scorecard.
import { useCallback, useEffect, useRef, useState } from "react";
import { postCompare } from "../api/client";
import type { CompareResponse, Scorecard as ScorecardData, SceneControls } from "../api/client";
import { ControlRail } from "../components/ControlRail";
import type { Controls } from "../components/ControlRail";
import { FieldCanvas } from "../components/FieldCanvas";
import { Rail } from "../components/Rail";
import { Scorecard } from "../components/Scorecard";

const DEFAULTS: Controls = {
  layout: "single",
  electrode_um: 10,
  pitch_um: 60,
  phase_width_us: 200,
  neighbor_um: 40,
  sigma_S_per_m: 1,
};

const asRequest = (c: Controls, includeScorecard: boolean): SceneControls => ({
  ...c,
  extent_um: 130,
  n: 61,
  include_scorecard: includeScorecard,
});

export function Compare() {
  const [controls, setControls] = useState<Controls>(DEFAULTS);
  const [scene, setScene] = useState<CompareResponse | null>(null);
  const [scorecard, setScorecard] = useState<ScorecardData | null>(null);
  const [scoring, setScoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  // live field preview, debounced; the scorecard is not requested here
  useEffect(() => {
    const ticket = ++latest.current;
    const ctrl = new AbortController();
    setScorecard(null); // the operating window no longer matches these controls
    const timer = setTimeout(() => {
      postCompare(asRequest(controls, false), ctrl.signal)
        .then((res) => {
          if (ticket === latest.current) {
            setScene(res);
            setError(null);
          }
        })
        .catch((e: unknown) => {
          if (ticket === latest.current && !ctrl.signal.aborted) {
            setError(e instanceof Error ? e.message : "request failed");
          }
        });
    }, 160);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [controls]);

  const runScorecard = useCallback(() => {
    setScoring(true);
    postCompare(asRequest(controls, true))
      .then((res) => setScorecard(res.scorecard ?? { activated: false }))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "scoring failed"))
      .finally(() => setScoring(false));
  }, [controls]);

  const layoutName = controls.layout === "bipolar" ? "Bipolar · local return" : "Monopolar";

  return (
    <div className="app">
      <Rail active="Compare" tier="Analytical" safe="field only" />
      <main className="stage">
        <div className="stage-head">
          <div>
            <h1>
              {layoutName} · {controls.electrode_um} µm disk
            </h1>
            <div className="crumb">
              live analytical field · target + neighbour at {controls.neighbor_um} µm
            </div>
          </div>
        </div>
        {error && (
          <div className="card panel" role="alert">
            <p className="empty">
              Couldn’t reach the field engine ({error}). Is the API running on :8000?
            </p>
          </div>
        )}
        <FieldCanvas data={scene} />
      </main>
      <aside className="inspect">
        <ControlRail controls={controls} onChange={setControls} />
        <Scorecard data={scorecard} loading={scoring} onRun={runScorecard} />
      </aside>
    </div>
  );
}
