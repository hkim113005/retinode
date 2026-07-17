// The Study screen: build a diameter × pitch sweep, run it as a job, and read the
// selectivity-versus-cost Pareto frontier — the design-explorer payoff. Click a
// frontier point to inspect its geometry and metrics.
import { useMemo, useRef, useState } from "react";
import { getJob, postStudy } from "../api/client";
import type { StudyControls, StudyPoint } from "../api/client";
import { ParetoPlot } from "../components/ParetoPlot";
import { Rail } from "../components/Rail";
import type { Screen } from "../nav";
import type { Progress } from "./Compare";

const DIAMETERS = [8, 12, 16, 20];
const PITCHES = [30, 40, 55, 70];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function Study({ onNavigate }: { onNavigate?: (s: Screen) => void }) {
  const [diameters, setDiameters] = useState<Set<number>>(new Set(DIAMETERS));
  const [pitches, setPitches] = useState<Set<number>>(new Set(PITCHES));
  const [points, setPoints] = useState<StudyPoint[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [selected, setSelected] = useState<StudyPoint | null>(null);
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
    setProgress({ fraction: 0, message: "submitting" });
    const controls: StudyControls = {
      diameters_um: [...diameters].sort((a, b) => a - b),
      pitches_um: [...pitches].sort((a, b) => a - b),
      arrangement: "hex",
      aperture_um: 120,
      phase_width_us: 200,
      neighbor_um: 40,
      sigma_S_per_m: 1,
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
      setPoints(job.study?.points ?? []);
    })()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "study failed"))
      .finally(() => {
        if (id === ticket.current) setProgress(null);
      });
  };

  const nFrontier = points.filter((p) => p.on_frontier && p.safe).length;

  return (
    <div className="app">
      <Rail active="Study" tier="Analytical" safe="filtered" onNavigate={onNavigate} />
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
            <p className="empty">Couldn’t run the study ({error}). Is the API running on :8000?</p>
          </div>
        )}
        <ParetoPlot points={points} selected={selected} onSelect={setSelected} />
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
          <div className="cost">
            <span className="n">{nCombos}</span>
            <span className="k">
              configurations
              <br />≈ {Math.max(5, nCombos * 3)} s · analytical field
            </span>
          </div>
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
