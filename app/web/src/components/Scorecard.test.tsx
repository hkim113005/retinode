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
    render(<Scorecard data={null} loading={false} onRun={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Run scorecard/ })).toBeInTheDocument();
  });

  it("renders the operating window when activated", () => {
    render(<Scorecard data={USABLE} loading={false} onRun={vi.fn()} />);
    expect(screen.getByText("8.0 µA")).toBeInTheDocument(); // target threshold
    expect(screen.getByText("usable")).toBeInTheDocument();
  });

  it("explains a non-activation cleanly", () => {
    render(<Scorecard data={{ activated: false }} loading={false} onRun={vi.fn()} />);
    expect(screen.getByText(/never fired/)).toBeInTheDocument();
  });
});
