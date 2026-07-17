// The Compare screen: control rail → live analytical field, plus an on-demand
// scorecard. Editing a control refetches the field (debounced, NEURON-free). The
// scorecard runs as a background job (a NEURON threshold search) — submit, then poll
// to completion — kept in separate state so a field refetch never clobbers it, and
// cleared when a control changes (the window no longer matches).
import { useCallback, useEffect, useRef, useState } from "react";
import { getJob, postCompare, postScore } from "../api/client";
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

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export interface Progress {
  fraction: number;
  message: string;
}

export function Compare() {
  const [controls, setControls] = useState<Controls>(DEFAULTS);
  const [scene, setScene] = useState<CompareResponse | null>(null);
  const [scorecard, setScorecard] = useState<ScorecardData | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [cached, setCached] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fieldTicket = useRef(0);
  const scoreTicket = useRef(0);

  // live field preview, debounced; the scorecard is not requested here
  useEffect(() => {
    const ticket = ++fieldTicket.current;
    scoreTicket.current++; // a control change invalidates any in-flight scoring
    setScorecard(null); // the operating window no longer matches these controls
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      postCompare(asRequest(controls, false), ctrl.signal)
        .then((res) => {
          if (ticket === fieldTicket.current) {
            setScene(res);
            setError(null);
          }
        })
        .catch((e: unknown) => {
          if (ticket === fieldTicket.current && !ctrl.signal.aborted) {
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
    const ticket = ++scoreTicket.current;
    setProgress({ fraction: 0, message: "submitting" });
    (async () => {
      let job = await postScore(asRequest(controls, false));
      while (job.status === "running") {
        if (ticket !== scoreTicket.current) return; // controls changed — abandon
        setProgress({ fraction: job.fraction, message: job.message });
        await sleep(400);
        job = await getJob(job.id);
      }
      if (ticket !== scoreTicket.current) return;
      if (job.status === "error") throw new Error(job.error ?? "scoring failed");
      setScorecard(job.scorecard ?? { activated: false });
      setCached(job.cached);
    })()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "scoring failed"))
      .finally(() => {
        if (ticket === scoreTicket.current) setProgress(null);
      });
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
        <Scorecard
          data={scorecard}
          progress={progress}
          cached={cached}
          onRun={runScorecard}
        />
      </aside>
    </div>
  );
}
