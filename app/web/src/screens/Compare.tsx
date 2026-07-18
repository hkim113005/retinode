// The Compare screen: control rail → live analytical field, an on-demand scorecard,
// and "Run accurately" (an FEM solve dispatched to the conda env). Editing a control
// refetches the analytical field (debounced) and resets any FEM/scorecard result,
// which no longer matches. The scorecard and the FEM field each run as a background
// job (submit then poll), kept in their own state so nothing clobbers anything else.
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getJob, postAccurateField, postCad, postCompare, postScore, postSweep } from "../api/client";
import type {
  AmplitudeSweep,
  CompareResponse,
  Scorecard as ScorecardData,
  SceneControls,
} from "../api/client";
import { ActivationPlot } from "../components/ActivationPlot";
import { useCommands } from "../components/Commands";
import { BODY_LABEL, ControlRail } from "../components/ControlRail";
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
  body: { kind: "none" },
  overlap_policy: "reject",
};

const asRequest = (c: Controls, includeScorecard: boolean): SceneControls => ({
  ...c,
  extent_um: 130,
  n: 61,
  include_scorecard: includeScorecard,
});

// The amplitude grid the sweep button uses. 24 points is ~24 × the population in
// NEURON runs — the same order as the scorecard this screen already runs, so it
// stays a seconds-long job.
//
// LOG, not linear, and that is not a style choice. Thresholds here land around
// 5–30 µA, so a linear 1–200 grid spends most of its points on the flat top and
// resolves the interesting end at ~8 µA per step — coarser than the gap between the
// target and its bystander. Measured: on a 10 µm disk, linear put BOTH cells at the
// same grid point (12.7 µA), reporting a zero-wide window; log separated them at
// 8.9 and 16.5. The linear grid did not merely look worse, it was wrong.
const SWEEP_GRID = {
  amp_min_uA: 1,
  amp_max_uA: 200,
  n_amplitudes: 24,
  spacing: "log",
} as const;

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
  const [sweep, setSweep] = useState<AmplitudeSweep | null>(null);
  const [sweepProgress, setSweepProgress] = useState<Progress | null>(null);
  const [sweepCached, setSweepCached] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fieldTicket = useRef(0);
  const scoreTicket = useRef(0);
  const femTicket = useRef(0);
  const sweepTicket = useRef(0);

  // live analytical field preview, debounced; resets stale FEM + scorecard results
  useEffect(() => {
    const ticket = ++fieldTicket.current;
    scoreTicket.current++;
    femTicket.current++;
    sweepTicket.current++;
    setScorecard(null);
    setSweep(null); // this grid was swept for a different scene
    setSweepCached(false);
    // clear the progress of any in-flight job too, not just its result: the job's
    // ticket is now stale so its own `.finally` guard declines to clear it, which
    // would otherwise orphan the progress bar and lock the action forever. Safe —
    // the poll loops re-check their ticket before every setProgress, so a superseded
    // job cannot re-populate what we clear here.
    setScoreProgress(null);
    setFemProgress(null);
    setSweepProgress(null);
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
      .catch((e: unknown) => {
        // don't surface a superseded job's failure — the scene has moved on
        if (ticket === scoreTicket.current) {
          setError(e instanceof Error ? e.message : "scoring failed");
        }
      })
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
      .catch((e: unknown) => {
        if (ticket === femTicket.current) {
          setError(e instanceof Error ? e.message : "FEM solve failed");
        }
      })
      .finally(() => {
        if (ticket === femTicket.current) setFemProgress(null);
      });
  }, [controls]);

  const runSweep = useCallback(() => {
    const ticket = ++sweepTicket.current;
    setSweepProgress({ fraction: 0, message: "submitting" });
    (async () => {
      let job = await postSweep({ ...asRequest(controls, false), ...SWEEP_GRID });
      while (job.status === "running") {
        if (ticket !== sweepTicket.current) return;
        setSweepProgress({ fraction: job.fraction, message: job.message });
        await sleep(400);
        job = await getJob(job.id);
      }
      if (ticket !== sweepTicket.current) return;
      if (job.status === "error") throw new Error(job.error ?? "the sweep failed");
      setSweep(job.sweep ?? null);
      setSweepCached(job.cached);
    })()
      .catch((e: unknown) => {
        if (ticket === sweepTicket.current) {
          setError(e instanceof Error ? e.message : "the sweep failed");
        }
      })
      .finally(() => {
        if (ticket === sweepTicket.current) setSweepProgress(null);
      });
  }, [controls]);

  const layoutName = controls.layout === "bipolar" ? "Bipolar · local return" : "Monopolar";
  // A 3D body is FEM-only: the analytical preview is a point source blind to geometry,
  // so we don't show it as "the field" — we prompt for the FEM solve instead.
  const bodied = controls.body.kind !== "none";
  const shapeName = bodied
    ? `${BODY_LABEL[controls.body.kind]} electrode`
    : `${controls.electrode_um} µm disk`;
  const showFemPrompt = bodied && tier !== "fem";

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
          id: "run-sweep",
          group: "Compare",
          label: "Sweep amplitudes",
          hint: sweepProgress ? "already running" : "NEURON · background job",
          disabled: !!sweepProgress,
          run: runSweep,
        },
        {
          id: "reset-controls",
          group: "Compare",
          label: "Reset the configuration",
          hint: "back to defaults",
          run: () => setControls(DEFAULTS),
        },
      ],
      [runScorecard, runAccurate, runSweep, scoreProgress, femProgress, sweepProgress, controls.layout],
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
              {layoutName} · {shapeName}
            </h1>
            <div className="crumb">
              {bodied ? "3D electrode · FEM required" : "live analytical field"} · target +
              neighbour at {controls.neighbor_um} µm
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
          <span className={`tierchip ${tier}`}>
            {tier === "fem" ? "FEM ✓ inked" : bodied ? "3D · FEM required" : "Analytical"}
          </span>
          {tier === "fem" && divergence != null && (
            <span className="diverge">differs from the analytical preview by up to {divergence.toFixed(0)}%</span>
          )}
          <span className="spacer" />
          {femProgress ? (
            <span className="running">{femProgress.message}…</span>
          ) : (
            <button className="btn small" onClick={runAccurate}>
              {bodied ? "Run field (FEM)" : "Run accurately (FEM)"}
            </button>
          )}
        </div>
        <div className="field-stack">
          {/* the plot and the 3D scene each fail alone: losing the loupe (WebGL is
              not guaranteed) must not cost the field, and neither costs the controls */}
          <ErrorBoundary what="The field">
            {showFemPrompt ? (
              <div className="card panel field-3d-notice" role="note">
                <p className="empty">
                  {BODY_LABEL[controls.body.kind]} electrode — the analytical preview is a
                  point source and can’t represent electrode geometry. Run the FEM field
                  (button above) for the real potential; it also drives the scorecard.
                </p>
              </div>
            ) : (
              <FieldCanvas data={scene} tier={tier} />
            )}
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
        <ErrorBoundary what="The activation plot">
          <ActivationPlot
            data={sweep}
            scorecard={scorecard}
            progress={sweepProgress}
            cached={sweepCached}
            onRun={runSweep}
          />
        </ErrorBoundary>
        <History runs={runs} current={runKey(controls)} onRestore={setControls} />
      </main>
      <aside className="inspect">
        <ControlRail controls={controls} onChange={setControls} uploadCad={postCad} />
        <Scorecard data={scorecard} progress={scoreProgress} cached={cached} onRun={runScorecard} />
      </aside>
    </div>
  );
}
