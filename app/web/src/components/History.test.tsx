import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Scorecard as ScorecardData } from "../api/client";
import type { Controls } from "./ControlRail";
import { History, MAX_RUNS, remember, runKey } from "./History";
import type { Run } from "./History";

const C: Controls = {
  layout: "single",
  electrode_um: 10,
  pitch_um: 60,
  phase_width_us: 200,
  neighbor_um: 40,
  sigma_S_per_m: 1,
  body: { kind: "none" },
  overlap_policy: "reject",
};

const CARD: ScorecardData = {
  activated: true,
  target_uA: 8,
  off_min_uA: 12,
  ratio: 1.5,
  usable_margin_uA: 4,
  usable: true,
  limiting: "off_target",
};

const run = (electrode_um: number): Run => {
  const controls = { ...C, electrode_um };
  return { id: runKey(controls), controls, scorecard: CARD };
};

describe("runKey", () => {
  it("is the same for the same configuration and differs otherwise", () => {
    expect(runKey(C)).toBe(runKey({ ...C }));
    expect(runKey(C)).not.toBe(runKey({ ...C, sigma_S_per_m: 1.4 }));
    // conductivity must take part: it changes the physics, so it is a different run
    expect(runKey({ ...C, sigma_S_per_m: 0.5 })).not.toBe(runKey({ ...C, sigma_S_per_m: 2 }));
    // a 3D body + overlap policy change the score, so they must key distinctly from
    // the flat disk of the same footprint (else a pillar would masquerade as its disk)
    const pillar: Controls = {
      ...C,
      body: { kind: "cylinder", radius_um: 5, height_um: 30, conductive_faces: "tip" },
    };
    expect(runKey(pillar)).not.toBe(runKey(C));
    expect(runKey(pillar)).not.toBe(runKey({ ...pillar, overlap_policy: "displace" }));
  });
});

describe("remember", () => {
  it("puts the newest first", () => {
    const rs = remember(remember([], run(10)), run(20));
    expect(rs.map((r) => r.controls.electrode_um)).toEqual([20, 10]);
  });

  it("moves a re-run configuration back to the front rather than duplicating it", () => {
    const rs = remember(remember(remember([], run(10)), run(20)), run(10));
    expect(rs.map((r) => r.controls.electrode_um)).toEqual([10, 20]);
  });

  it("keeps only the most recent MAX_RUNS", () => {
    let rs: Run[] = [];
    for (let i = 0; i < MAX_RUNS + 3; i++) rs = remember(rs, run(i));
    expect(rs).toHaveLength(MAX_RUNS);
    expect(rs[0].controls.electrode_um).toBe(MAX_RUNS + 2); // the newest survives
    expect(rs.some((r) => r.controls.electrode_um === 0)).toBe(false); // the oldest fell off
  });
});

describe("History", () => {
  it("renders nothing before anything has been scored", () => {
    const { container } = render(<History runs={[]} current="" onRestore={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("restores the whole configuration of the run that was clicked", () => {
    const onRestore = vi.fn();
    const r = run(24);
    render(<History runs={[r]} current="" onRestore={onRestore} />);
    fireEvent.click(screen.getByRole("button", { name: /Restore 24 µm/ }));
    expect(onRestore).toHaveBeenCalledWith(r.controls);
  });

  it("leads with the window and ratio, and marks the run being viewed", () => {
    const r = run(10);
    render(<History runs={[r, run(20)]} current={r.id} onRestore={vi.fn()} />);
    expect(screen.getAllByText("4.0 µA").length).toBe(2);
    expect(screen.getAllByText("1.50×").length).toBe(2);
    expect(screen.getByRole("button", { name: /Restore 10 µm/ })).toHaveClass("on");
    expect(screen.getByRole("button", { name: /Restore 20 µm/ })).not.toHaveClass("on");
  });

  it("flags a run the engine would refuse to compare, rather than showing a difference", () => {
    // the engine's require_same_offtarget: a window scored against different
    // bystanders is not comparable. Unreachable from the UI today (the off-target
    // policy has no control), but the strip must never present it as a difference.
    const newest: Run = { ...run(10), scorecard: { ...CARD, offtarget_hash: "aaa" } };
    const older: Run = { ...run(20), scorecard: { ...CARD, offtarget_hash: "bbb" } };
    render(<History runs={[newest, older]} current="" onRestore={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/not comparable with the latest/);
    expect(screen.getByRole("button", { name: /Restore 20 µm.*different off-target set/ })).toHaveClass("odd");
    expect(screen.getByRole("button", { name: /Restore 10 µm/ })).not.toHaveClass("odd");
  });

  it("says nothing when every run shares an off-target set — the normal case", () => {
    const a: Run = { ...run(10), scorecard: { ...CARD, offtarget_hash: "aaa" } };
    const b: Run = { ...run(20), scorecard: { ...CARD, offtarget_hash: "aaa" } };
    render(<History runs={[a, b]} current="" onRestore={vi.fn()} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Restore 20 µm/ })).not.toHaveClass("odd");
  });

  it("shows an unbounded window as ∞ and a dead configuration honestly", () => {
    const inf: Run = { ...run(10), scorecard: { ...CARD, usable_margin_uA: Number.POSITIVE_INFINITY } };
    const dead: Run = { ...run(20), scorecard: { activated: false } };
    render(<History runs={[inf, dead]} current="" onRestore={vi.fn()} />);
    expect(screen.getByText("∞")).toBeInTheDocument();
    expect(screen.getByText("no window")).toBeInTheDocument();
    expect(screen.queryByText(/Infinity/)).not.toBeInTheDocument();
  });
});
