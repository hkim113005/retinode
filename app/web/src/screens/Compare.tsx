// The Compare screen: control rail → live analytical field, an on-demand scorecard,
// and "Run accurately" (an FEM solve dispatched to the conda env). Editing a control
// refetches the analytical field (debounced) and resets any FEM/scorecard result,
// which no longer matches. The scorecard and the FEM field each run as a background
// job (submit then poll), kept in their own state so nothing clobbers anything else.
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getJob, postAccurateField, postCompare, postScore } from "../api/client";
import type { CompareResponse, Scorecard as ScorecardData, SceneControls } from "../api/client";
import { useCommands } from "../components/Commands";
import { ControlRail } from "../components/ControlRail";
import type { Controls } from "../components/ControlRail";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { FieldCanvas } from "../components/FieldCanvas";
import { History, remember, runKey } from "../components/History";
import type { Run } from "../components/History";
import { Rail } from "../components/Rail";
import { Scorecard } from "../components/Scorecard";
import { ThresholdPlot } from "../components/ThresholdPlot";
import type { Screen } from "../nav";

// three.js is heavy and only needed for the 3D loupe — lazy-load it so it stays off
// the main chunk (and out of the synchronous test path).
const Loupe3D = lazy(() => import("../components/Loupe3D"));

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

export function Compare({ onNavigate }: { onNavigate?: (s: Screen) => void }) {
  const [controls, setControls] = useState<Controls>(DEFAULTS);
  const [scene, setScene] = useState<CompareResponse | null>(null);
  const [tier, setTier] = useState<"analytical" | "fem">("analytical");
  const [divergence, setDivergence] = useState<number | null>(null);
  const [femProgress, setFemProgress] = useState<Progress | null>(null);
  const [scorecard, setScorecard] = useState<ScorecardData | null>(null);
  const [scoreProgress, setScoreProgress] = useState<Progress | null>(null);
  const [cached, setCached] = useState(false);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);
  const fieldTicket = useRef(0);
  const scoreTicket = useRef(0);
  const femTicket = useRef(0);

  // live analytical field preview, debounced; resets stale FEM + scorecard results
  useEffect(() => {
    const ticket = ++fieldTicket.current;
    scoreTicket.current++;
    femTicket.current++;
    setScorecard(null);
    setTier("analytical");
    setDivergence(null);
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
    setScoreProgress({ fraction: 0, message: "submitting" });
    (async () => {
      let job = await postScore(asRequest(controls, false));
      while (job.status === "running") {
        if (ticket !== scoreTicket.current) return;
        setScoreProgress({ fraction: job.fraction, message: job.message });
        await sleep(400);
        job = await getJob(job.id);
      }
      if (ticket !== scoreTicket.current) return;
      if (job.status === "error") throw new Error(job.error ?? "scoring failed");
      const card = job.scorecard ?? { activated: false };
      setScorecard(card);
      setCached(job.cached);
      // a scorecard costs a threshold search — keep it so two designs can be
      // compared without re-running one from memory
      setRuns((rs) => remember(rs, { id: runKey(controls), controls, scorecard: card }));
    })()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "scoring failed"))
      .finally(() => {
        if (ticket === scoreTicket.current) setScoreProgress(null);
      });
  }, [controls]);

  const runAccurate = useCallback(() => {
    const ticket = ++femTicket.current;
    setFemProgress({ fraction: 0, message: "submitting" });
    (async () => {
      let job = await postAccurateField(asRequest(controls, false));
      while (job.status === "running") {
        if (ticket !== femTicket.current) return;
        setFemProgress({ fraction: job.fraction, message: job.message });
        await sleep(800);
        job = await getJob(job.id);
      }
      if (ticket !== femTicket.current) return;
      if (job.status === "error") throw new Error(job.error ?? "FEM solve failed");
      if (job.field) {
        setScene((prev) => (prev ? { ...prev, field: job.field! } : prev));
        setTier("fem");
        setDivergence(job.max_divergence_pct ?? null);
      }
    })()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "FEM solve failed"))
      .finally(() => {
        if (ticket === femTicket.current) setFemProgress(null);
      });
  }, [controls]);

  const layoutName = controls.layout === "bipolar" ? "Bipolar · local return" : "Monopolar";

  useCommands(
    "compare",
    useMemo(
      () => [
        {
          id: "run-scorecard",
          group: "Compare",
          label: "Run scorecard",
          hint: scoreProgress ? "already running" : "NEURON · background job",
          disabled: !!scoreProgress,
          run: runScorecard,
        },
        {
          id: "run-fem",
          group: "Compare",
          label: "Run accurately (FEM)",
          hint: femProgress ? "already running" : "conda env · background job",
          disabled: !!femProgress,
          run: runAccurate,
        },
        {
          id: "toggle-return",
          group: "Compare",
          label: controls.layout === "bipolar" ? "Switch to monopolar" : "Switch to bipolar return",
          run: () =>
            setControls((c) => ({ ...c, layout: c.layout === "bipolar" ? "single" : "bipolar" })),
        },
        {
          id: "reset-controls",
          group: "Compare",
          label: "Reset the configuration",
          hint: "back to defaults",
          run: () => setControls(DEFAULTS),
        },
      ],
      [runScorecard, runAccurate, scoreProgress, femProgress, controls.layout],
    ),
  );

  return (
    <div className="app">
      <Rail
        active="Compare"
        tier={tier === "fem" ? "FEM" : "Analytical"}
        safe="field only"
        onNavigate={onNavigate}
      />
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
        <div className="fieldbar card">
          <span className={`tierchip ${tier}`}>{tier === "fem" ? "FEM ✓ inked" : "Analytical"}</span>
          {tier === "fem" && divergence != null && (
            <span className="diverge">differs from the analytical preview by up to {divergence.toFixed(0)}%</span>
          )}
          <span className="spacer" />
          {femProgress ? (
            <span className="running">{femProgress.message}…</span>
          ) : (
            <button className="btn small" onClick={runAccurate}>
              Run accurately (FEM)
            </button>
          )}
        </div>
        <div className="field-stack">
          {/* the plot and the 3D scene each fail alone: losing the loupe (WebGL is
              not guaranteed) must not cost the field, and neither costs the controls */}
          <ErrorBoundary what="The field">
            <FieldCanvas data={scene} tier={tier} />
          </ErrorBoundary>
          <ErrorBoundary what="The 3D loupe">
            <Suspense fallback={null}>
              <Loupe3D electrodes={scene?.electrodes ?? []} cells={scene?.cells ?? []} tier={tier} />
            </Suspense>
          </ErrorBoundary>
        </div>
        <ErrorBoundary what="The threshold plot">
          <ThresholdPlot data={scorecard} />
        </ErrorBoundary>
        <History runs={runs} current={runKey(controls)} onRestore={setControls} />
      </main>
      <aside className="inspect">
        <ControlRail controls={controls} onChange={setControls} />
        <Scorecard data={scorecard} progress={scoreProgress} cached={cached} onRun={runScorecard} />
      </aside>
    </div>
  );
}
