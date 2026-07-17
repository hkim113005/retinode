// The Study screen: build a diameter × pitch sweep, run it as a job, and read the
// selectivity-versus-cost Pareto frontier — the design-explorer payoff. Click a
// frontier point to inspect its geometry and metrics.
import { useMemo, useRef, useState } from "react";
import { getJob, postStudy } from "../api/client";
import type { StudyControls, StudyPoint } from "../api/client";
import { useCommands } from "../components/Commands";
import { ParetoPlot } from "../components/ParetoPlot";
import { Rail } from "../components/Rail";
import type { Screen } from "../nav";
import type { Progress } from "./Compare";

const DIAMETERS = [8, 12, 16, 20];
const PITCHES = [30, 40, 55, 70];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function Study({
  onNavigate,
  onPoints,
  onFocus,
  points: initialPoints = [],
}: {
  onNavigate?: (s: Screen) => void;
  onPoints?: (p: StudyPoint[]) => void; // lift the sweep so it carries to Candidates
  onFocus?: (p: StudyPoint[] | null) => void; // a brushed subset to shortlist
  points?: StudyPoint[];
}) {
  const [diameters, setDiameters] = useState<Set<number>>(new Set(DIAMETERS));
  const [pitches, setPitches] = useState<Set<number>>(new Set(PITCHES));
  const [points, setPoints] = useState<StudyPoint[]>(initialPoints);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [selected, setSelected] = useState<StudyPoint | null>(null);
  const [brushed, setBrushed] = useState<StudyPoint[] | null>(null);
  const [spread, setSpread] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ticket = useRef(0);

  // valid combos = the Cartesian product minus overlaps (pitch < diameter)
  const nCombos = useMemo(() => {
    let n = 0;
    for (const d of diameters) for (const p of pitches) if (p >= d) n++;
    return n;
  }, [diameters, pitches]);

  const toggle = (set: Set<number>, apply: (s: Set<number>) => void, v: number) => {
    const next = new Set(set);
    next.has(v) ? next.delete(v) : next.add(v);
    apply(next);
  };

  const runStudy = () => {
    const id = ++ticket.current;
    setSelected(null);
    setBrushed(null); // a new sweep invalidates the old selection
    setProgress({ fraction: 0, message: "submitting" });
    const controls: StudyControls = {
      diameters_um: [...diameters].sort((a, b) => a - b),
      pitches_um: [...pitches].sort((a, b) => a - b),
      arrangement: "hex",
      aperture_um: 120,
      phase_width_us: 200,
      neighbor_um: 40,
      sigma_S_per_m: 1,
      // K axon trajectories per geometry for the threshold error bar. 1 = off, and
      // off is the default: it costs K extra threshold searches per geometry.
      trajectory_k: spread ? 3 : 1,
      trajectory_jitter_deg: 15,
    };
    (async () => {
      let job = await postStudy(controls);
      while (job.status === "running") {
        if (id !== ticket.current) return;
        setProgress({ fraction: job.fraction, message: job.message });
        await sleep(500);
        job = await getJob(job.id);
      }
      if (id !== ticket.current) return;
      if (job.status === "error") throw new Error(job.error ?? "study failed");
      const found = job.study?.points ?? [];
      setPoints(found);
      onPoints?.(found); // carries to Candidates
    })()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "study failed"))
      .finally(() => {
        if (id === ticket.current) setProgress(null);
      });
  };

  const nFrontier = points.filter((p) => p.on_frontier && p.safe).length;

  // A FEM solve + NEURON thresholds is ~28s per geometry (measured on a 2-geometry
  // run: 55s). Trajectory sampling reruns the field per axon path, so it multiplies
  // per-geometry cost by roughly (1 + k). Rounded up, shown honestly as minutes.
  const estimate = useMemo(() => {
    const perGeom = 28 * (spread ? 4 : 1);
    const secs = 20 + nCombos * perGeom;
    return secs < 90 ? `${Math.round(secs)} s` : `${Math.ceil(secs / 60)} min`;
  }, [nCombos, spread]);

  useCommands(
    "study",
    useMemo(
      () => [
        {
          id: "run-study",
          group: "Study",
          label: `Run the sweep (${nCombos} configurations)`,
          hint: progress ? "already running" : "background job",
          disabled: !!progress || nCombos === 0,
          run: runStudy,
        },
        {
          id: "clear-brush",
          group: "Study",
          label: "Clear the brushed selection",
          disabled: !brushed,
          run: () => setBrushed(null),
        },
      ],
      [runStudy, progress, nCombos, brushed],
    ),
  );

  return (
    <div className="app">
      <Rail active="Study" tier="FEM" safe="filtered" onNavigate={onNavigate} />
      <main className="stage">
        <div className="stage-head">
          <div>
            <h1>Study · diameter × pitch</h1>
            <div className="crumb">
              {points.length
                ? `${points.length} geometries · ${nFrontier} on the frontier · click to inspect`
                : "selectivity vs. current on the Pareto frontier"}
            </div>
          </div>
        </div>
        {error && (
          <div className="card panel" role="alert">
            <p className="empty">Couldn’t run the study: {error}</p>
          </div>
        )}
        <ParetoPlot
          points={points}
          selected={selected}
          onSelect={setSelected}
          onBrush={setBrushed}
        />
      </main>
      <aside className="inspect">
        <div className="card panel">
          <h2>Build the sweep</h2>
          <div className="ctl">
            <label>Electrode diameter (µm)</label>
            <div className="chips">
              {DIAMETERS.map((d) => (
                <button
                  key={d}
                  className={diameters.has(d) ? "on" : ""}
                  onClick={() => toggle(diameters, setDiameters, d)}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
          <div className="ctl">
            <label>Pitch (µm)</label>
            <div className="chips">
              {PITCHES.map((p) => (
                <button
                  key={p}
                  className={pitches.has(p) ? "on" : ""}
                  onClick={() => toggle(pitches, setPitches, p)}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
          <div className="ctl">
            <label htmlFor="c-spread">
              Axon-trajectory error bar<b>{spread ? "3 paths" : "off"}</b>
            </label>
            <div className="seg" role="group" aria-label="Axon-trajectory sampling">
              <button className={spread ? "" : "on"} onClick={() => setSpread(false)}>
                Off
              </button>
              <button className={spread ? "on" : ""} onClick={() => setSpread(true)}>
                Sample 3
              </button>
            </div>
            <p className="foot">
              The true axon path is unknown, so a threshold has a band. Sampling
              measures it — but reruns the FEM field per path, so it multiplies the
              already-minutes sweep cost several-fold.
            </p>
          </div>
          <div className="cost">
            <span className="n">{nCombos}</span>
            <span className="k">
              configurations
              <br />≈ {estimate} · FEM (accurate)
            </span>
          </div>
          <p className="foot">
            Comparing electrode geometry needs the FEM field — the analytical tier is a
            point source and cannot tell one diameter from another. So this runs
            accurately, in the FEM env, in minutes rather than seconds.
          </p>
          {progress ? (
            <>
              <p className="empty">{progress.message}…</p>
              <div className="progress">
                <span style={{ width: `${Math.round(progress.fraction * 100)}%` }} />
              </div>
            </>
          ) : (
            <button className="btn" onClick={runStudy} disabled={nCombos === 0}>
              Run study
            </button>
          )}
        </div>

        {brushed && (
          <div className="card panel">
            <h2>Brushed selection</h2>
            <div className="verdict">
              <span className="big">{brushed.length}</span>
              <span className="pill win">charge-safe designs</span>
            </div>
            <p className="empty">
              {brushed.length === 1
                ? `d${brushed[0].diameter_um} · pitch ${brushed[0].pitch_um} µm.`
                : `${brushed.filter((p) => p.on_frontier).length} of them sit on the frontier.`}
            </p>
            <button
              className="btn"
              onClick={() => {
                onFocus?.(brushed);
                onNavigate?.("Candidates");
              }}
            >
              Shortlist these {brushed.length} →
            </button>
            <button className="btn ghost small" onClick={() => setBrushed(null)}>
              Clear
            </button>
          </div>
        )}

        <div className="card panel">
          <h2>Selected geometry</h2>
          {selected ? (
            <>
              <div className="verdict">
                <span className="big">
                  d{selected.diameter_um} · p{selected.pitch_um}
                </span>
                {selected.on_frontier && <span className="pill win">frontier</span>}
              </div>
              <div className="rows">
                <div className="row">
                  <span className="k">Target threshold</span>
                  <span className="v warm">{selected.cost_uA.toFixed(1)} µA</span>
                </div>
                <div className="row">
                  <span className="k">Selective window</span>
                  <span className="v ok">{selected.selectivity_uA.toFixed(1)} µA</span>
                </div>
                <div className="row">
                  <span className="k">Charge</span>
                  <span className={`v ${selected.safe ? "ok" : "alert"}`}>
                    {selected.safe ? "safe" : "over limit"}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="empty">Click a point on the frontier to inspect its geometry.</p>
          )}
        </div>
      </aside>
    </div>
  );
}
