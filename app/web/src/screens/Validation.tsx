// The Validation screen: the trust panel. Which published/physics reproductions
// currently pass, with the evidence — the claim, its source, what was measured, and
// the criterion. This is the committed report CI regenerates; the app renders it and
// never recomputes the science, so a skeptic sees exactly what the suite last proved
// (master plan §15).
import { useEffect, useState } from "react";
import { getValidation } from "../api/client";
import type { ValidationReport } from "../api/client";
import { Rail } from "../components/Rail";
import type { Screen } from "../nav";

export function Validation({ onNavigate }: { onNavigate?: (s: Screen) => void }) {
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getValidation()
      .then((r) => live && setReport(r))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : "failed"));
    return () => {
      live = false;
    };
  }, []);

  const allPass = report != null && report.n_pass === report.n_total && report.n_total > 0;

  return (
    <div className="app">
      <Rail
        active="Validation"
        tier={report ? `${report.n_pass}/${report.n_total}` : "—"}
        safe={allPass ? "all pass" : "see below"}
        onNavigate={onNavigate}
      />
      <main className="stage">
        <div className="stage-head">
          <div>
            <h1>Validation · what reproduces</h1>
            <div className="crumb">
              the committed report CI regenerates — rendered, never recomputed here
            </div>
          </div>
        </div>

        {error && (
          <div className="card panel" role="alert">
            <p className="empty">Couldn’t load the report ({error}). Is the API running on :8000?</p>
          </div>
        )}

        {report && (
          <div className="card panel">
            <div className="verdict">
              <span className="big">
                {report.n_pass}/{report.n_total}
              </span>
              <span className={`pill ${allPass ? "win" : "lost"}`}>
                {allPass ? "all reproduce" : "some failing"}
              </span>
            </div>
            <div className="sub">
              physics invariants and published results the engine currently reproduces
            </div>
          </div>
        )}

        {report && (
          <div className="card listcard">
            {report.reproductions.map((r, i) => (
              <div className="rep" key={i}>
                <span className={`tag ${r.passed ? "ok" : "bad"}`}>{r.passed ? "pass" : "fail"}</span>
                <div className="rep-body">
                  <div className="rep-name">{r.name}</div>
                  <div className="rep-meta">
                    <span className="src">{r.source}</span>
                    <span className="crit">criterion: {r.criterion}</span>
                  </div>
                  {r.measured && <div className="rep-measured">{r.measured}</div>}
                  {r.note && <div className="rep-note">{r.note}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
      <aside className="inspect">
        <div className="card panel">
          <h2>Why this screen exists</h2>
          <p className="empty">
            A ranking is only worth as much as the engine behind it. This panel lets a
            skeptical reader check the tool’s credibility <i>before</i> believing its
            candidates — each row names the claim, its source, and the measurement.
          </p>
          <div className="foot">
            The bar is trend and direction, not absolute magnitude (analytical tier +
            mouse RGC morphology). Deferrals are recorded in the project plan rather
            than tuned away.
          </div>
        </div>
      </aside>
    </div>
  );
}
