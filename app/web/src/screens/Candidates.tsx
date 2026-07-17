// The Candidates screen: the payoff. A ranked, safety-filtered shortlist of the
// designs worth testing in tissue — each with its threshold, selective window, charge
// verdict, accuracy tier, and a one-line rationale — exportable for the lab. It reads
// the study's points, so the flow is: sweep on Study → hand this list to someone.
import { useMemo } from "react";
import type { StudyPoint } from "../api/client";
import { downloadText as download } from "../chart/export";
import { Rail } from "../components/Rail";
import type { Screen } from "../nav";

const TOP_N = 8;

function rationale(p: StudyPoint, all: StudyPoint[]): string {
  const maxSel = Math.max(...all.map((q) => q.selectivity_uA));
  const minCost = Math.min(...all.map((q) => q.cost_uA));
  if (p.selectivity_uA === maxSel && p.cost_uA === minCost)
    return "Widest selective window and the lowest current — it dominates the safe set.";
  if (p.selectivity_uA === maxSel) return "The widest selective window in this study.";
  if (p.cost_uA === minCost) return "The lowest current of the safe set.";
  if (p.on_frontier)
    return "On the selectivity–cost frontier: no safe design beats it on both axes.";
  return "Beaten on both axes by a frontier design — listed for reference.";
}

export function Candidates({
  points,
  onNavigate,
}: {
  points: StudyPoint[];
  onNavigate?: (s: Screen) => void;
}) {
  // safety-filtered by definition, then ranked by the selective window
  const ranked = useMemo(
    () =>
      points
        .filter((p) => p.safe)
        .slice()
        .sort((a, b) => b.selectivity_uA - a.selectivity_uA)
        .slice(0, TOP_N),
    [points],
  );
  const best = ranked[0];

  const rows = () =>
    ranked.map((p, i) => ({
      rank: i + 1,
      diameter_um: p.diameter_um,
      pitch_um: p.pitch_um,
      target_threshold_uA: Number(p.cost_uA.toFixed(2)),
      selective_window_uA: Number(p.selectivity_uA.toFixed(2)),
      charge_safe: p.safe,
      on_frontier: p.on_frontier,
      tier: "analytical",
      rationale: rationale(p, ranked),
    }));

  const exportJson = () =>
    download("candidates.json", "application/json", JSON.stringify({ candidates: rows() }, null, 2));

  const exportCsv = () => {
    const r = rows();
    const head = Object.keys(r[0] ?? {}).join(",");
    const body = r.map((x) => Object.values(x).map((v) => `"${String(v)}"`).join(",")).join("\n");
    download("candidates.csv", "text/csv", `${head}\n${body}`);
  };

  return (
    <div className="app">
      <Rail
        active="Candidates"
        tier="Analytical"
        safe={ranked.length ? "filtered" : "—"}
        onNavigate={onNavigate}
      />
      <main className="stage">
        <div className="stage-head">
          <div>
            <h1>Candidates · worth testing in tissue</h1>
            <div className="crumb">
              {ranked.length
                ? `${ranked.length} charge-safe designs · ranked by selective window`
                : "the payoff — a ranked shortlist to hand to the lab"}
            </div>
          </div>
        </div>

        {!ranked.length ? (
          <div className="card panel">
            <p className="empty">
              No candidates yet. Run a sweep on the Study screen — its charge-safe designs
              are ranked here, ready to export.
            </p>
            <button className="btn" onClick={() => onNavigate?.("Study")}>
              Go to Study
            </button>
          </div>
        ) : (
          <>
            {best && (
              <div className="card reco">
                <span className="rank">▲ Recommended</span>
                <div className="body">
                  <div className="name">
                    d{best.diameter_um} · pitch {best.pitch_um} µm
                  </div>
                  <div className="say">
                    The widest selective window (<b>{best.selectivity_uA.toFixed(1)} µA</b>) among the
                    charge-safe designs, at <b>{best.cost_uA.toFixed(1)} µA</b> on the target — the
                    one to take to tissue first.
                  </div>
                </div>
              </div>
            )}
            <div className="card listcard">
              {ranked.map((p, i) => (
                <div className="cand" key={`${p.diameter_um}-${p.pitch_um}`}>
                  <div className={`rk${i === 0 ? " top" : ""}`}>{i + 1}</div>
                  <div className="body">
                    <div className="name">
                      d{p.diameter_um} · pitch {p.pitch_um} µm
                    </div>
                    <div className="say">{rationale(p, ranked)}</div>
                  </div>
                  <div className="metrics">
                    <div className="m">
                      <span className="k">selective window</span>
                      <span className="v warm">{p.selectivity_uA.toFixed(1)} µA</span>
                    </div>
                    <div className="m">
                      <span className="k">target threshold</span>
                      <span className="v">{p.cost_uA.toFixed(1)} µA</span>
                    </div>
                  </div>
                  <div className="tags">
                    <span className="tag ana">analytical</span>
                    <span className="tag ok">charge-safe</span>
                    {p.on_frontier && <span className="tag front">frontier</span>}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </main>
      <aside className="inspect">
        <div className="card panel">
          <h2>Export for the lab</h2>
          <div className="exp">
            <button className="btn" onClick={exportJson} disabled={!ranked.length}>
              Export list (JSON)
            </button>
            <button className="btn ghost" onClick={exportCsv} disabled={!ranked.length}>
              Export table (CSV)
            </button>
          </div>
          <div className="foot">
            Machine-readable for the lab’s own tooling. Figure-quality report export
            lands with the charting layer.
          </div>
        </div>
        <div className="card panel">
          <h2>How to read this</h2>
          <p className="empty">
            Every row is charge-safe by construction — unsafe designs never reach this
            list. Ranked by the selective window: how much current headroom you have
            above the target’s threshold before a bystander fires.
          </p>
          <div className="foot">
            Tier is <b>analytical</b> — the sweep’s field. Confirm a shortlisted design
            with “Run accurately (FEM)” on Compare before committing to fabrication.
          </div>
        </div>
      </aside>
    </div>
  );
}
