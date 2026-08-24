import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Scorecard as ScorecardData } from "../api/client";
import { Scorecard } from "./Scorecard";

const USABLE: ScorecardData = {
  activated: true,
  target_uA: 8,
  off_min_uA: 12,
  ratio: 1.5,
  window_lo_uA: 8,
  window_hi_uA: 12,
  usable_margin_uA: 4,
  usable: true,
  limiting: "off_target",
  safety_ceiling_uA: 24,
  safe_at_target: true,
};

describe("Scorecard", () => {
  it("prompts to run when unscored", () => {
    render(<Scorecard data={null} progress={null} cached={false} onRun={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Run scorecard/ })).toBeInTheDocument();
  });

  it("shows the job's progress while running", () => {
    render(
      <Scorecard
        data={null}
        progress={{ fraction: 0.4, message: "solving thresholds" }}
        cached={false}
        onRun={vi.fn()}
      />,
    );
    expect(screen.getByText(/solving thresholds/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Run scorecard/ })).not.toBeInTheDocument();
  });

  it("renders the operating window when activated, with a cached badge", () => {
    render(<Scorecard data={USABLE} progress={null} cached onRun={vi.fn()} />);
    expect(screen.getByText("8.0 µA")).toBeInTheDocument(); // target threshold
    expect(screen.getByText("usable")).toBeInTheDocument();
    expect(screen.getByText("cached")).toBeInTheDocument();
  });

  it("explains a non-activation cleanly", () => {
    render(<Scorecard data={{ activated: false }} progress={null} cached={false} onRun={vi.fn()} />);
    expect(screen.getByText(/never fired/)).toBeInTheDocument();
  });

  it("reports the selectivity ratio and what closed the window", () => {
    render(<Scorecard data={USABLE} progress={null} cached={false} onRun={vi.fn()} />);
    expect(screen.getByText("1.50×")).toBeInTheDocument();
    // "limited by a bystander" vs "limited by the charge limit" is the design decision
    expect(screen.getByText("a bystander fires")).toBeInTheDocument();
  });

  it("names the charge limit when that is what bounds the window", () => {
    render(
      <Scorecard
        data={{ ...USABLE, limiting: "safety" }}
        progress={null}
        cached={false}
        onRun={vi.fn()}
      />,
    );
    expect(screen.getByText("the charge limit")).toBeInTheDocument();
  });

  it("renders an unbounded window as ∞ rather than the word Infinity", () => {
    // a real evaluator state: nothing off-target ever fires in the searched range
    render(
      <Scorecard
        data={{
          ...USABLE,
          off_min_uA: Number.POSITIVE_INFINITY,
          window_hi_uA: Number.POSITIVE_INFINITY,
          usable_margin_uA: Number.POSITIVE_INFINITY,
          ratio: Number.POSITIVE_INFINITY,
          limiting: "none",
        }}
        progress={null}
        cached={false}
        onRun={vi.fn()}
      />,
    );
    expect(screen.queryByText(/Infinity/)).not.toBeInTheDocument();
    expect(screen.getAllByText("∞").length).toBeGreaterThan(0);
    expect(screen.getByText("∞×")).toBeInTheDocument();
    expect(screen.getByText("nothing (unbounded)")).toBeInTheDocument();
  });
});
