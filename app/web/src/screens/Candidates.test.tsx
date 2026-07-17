import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { StudyPoint } from "../api/client";
import { Candidates } from "./Candidates";

const P = (
  d: number,
  pitch: number,
  cost: number,
  sel: number,
  safe = true,
  front = true,
  spread_uA: number | null = null,
): StudyPoint => ({
  diameter_um: d,
  pitch_um: pitch,
  cost_uA: cost,
  selectivity_uA: sel,
  safe,
  on_frontier: front,
  spread_uA,
});

const POINTS = [
  P(16, 40, 7.0, 6.0), // lowest current
  P(12, 40, 9.0, 11.0), // widest window -> should rank #1
  P(8, 55, 12.0, 4.0, false), // UNSAFE — must never appear
  P(20, 70, 8.0, 5.0, true, false), // dominated
];

describe("Candidates", () => {
  it("prompts to run a study when there is nothing to rank", () => {
    const onNavigate = vi.fn();
    render(<Candidates points={[]} onNavigate={onNavigate} />);
    expect(screen.getByText(/No candidates yet/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Go to Study/ }));
    expect(onNavigate).toHaveBeenCalledWith("Study");
  });

  it("filters unsafe designs out and ranks by the selective window", () => {
    render(<Candidates points={POINTS} onNavigate={vi.fn()} />);
    // the unsafe 8 µm design must not be listed at all
    expect(screen.queryByText(/d8 · pitch 55/)).not.toBeInTheDocument();
    // 3 safe designs, the widest window first — and it headlines the recommendation
    expect(screen.getAllByText(/d12 · pitch 40/).length).toBeGreaterThan(0);
    expect(screen.getByText(/▲ Recommended/)).toBeInTheDocument();
    expect(screen.getByText("The widest selective window in this study.")).toBeInTheDocument();
    expect(screen.getByText("The lowest current in this study.")).toBeInTheDocument();
    expect(
      screen.getByText("Beaten on both axes by a frontier design — listed for reference."),
    ).toBeInTheDocument();
  });

  it("says its superlatives are about the brush, not the whole study", () => {
    // "the widest window in this study" would be a lie when only a corner was ranked
    render(<Candidates points={POINTS} onNavigate={vi.fn()} brushed />);
    expect(
      screen.getByText("The widest selective window in your brushed selection."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/in this study/)).not.toBeInTheDocument();
    expect(screen.getByText("brushed from the study")).toBeInTheDocument();
  });

  it("exports the shortlist as JSON", () => {
    const click = vi.fn();
    const createEl = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = createEl(tag);
      if (tag === "a") el.click = click;
      return el;
    });
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();

    render(<Candidates points={POINTS} onNavigate={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Export list \(JSON\)/ }));
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    vi.restoreAllMocks();
  });
});

describe("Candidates · the trajectory whisker", () => {
  // the true axon path is unknown, so a threshold has an honest band
  const MEASURED = [
    P(12, 40, 9.0, 11.0, true, true, 2.4), // widest window, but a loose error bar
    P(16, 40, 7.0, 6.0, true, true, 0.3), // tightest — the robust choice
  ];

  it("shows the error bar beside the threshold it qualifies", () => {
    render(<Candidates points={MEASURED} onNavigate={vi.fn()} />);
    expect(screen.getByText(/±2.4/)).toBeInTheDocument();
    expect(screen.getByText(/±0.3/)).toBeInTheDocument();
  });

  it("shows no whisker at all when the spread was not measured", () => {
    // absent, never a confident-looking ±0 on a design nobody measured
    render(<Candidates points={[P(12, 40, 9, 11)]} onNavigate={vi.fn()} />);
    expect(screen.queryByText(/±/)).not.toBeInTheDocument();
  });

  it("ranks by robustness when asked, tightest band first", () => {
    render(<Candidates points={MEASURED} onNavigate={vi.fn()} />);
    // by default the widest window leads
    expect(screen.getAllByText(/d\d+ · pitch/)[0]).toHaveTextContent("d12");
    fireEvent.click(screen.getByRole("button", { name: "robustness" }));
    // now the tightest error bar leads, even though its window is narrower
    expect(screen.getAllByText(/d\d+ · pitch/)[0]).toHaveTextContent("d16");
  });

  it("refuses to rank by a column the study never measured", () => {
    render(<Candidates points={[P(12, 40, 9, 11), P(16, 40, 7, 6)]} onNavigate={vi.fn()} />);
    expect(screen.getByRole("button", { name: "robustness" })).toBeDisabled();
  });

  it("ranks by threshold, cheapest first", () => {
    render(<Candidates points={MEASURED} onNavigate={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "threshold" }));
    expect(screen.getAllByText(/d\d+ · pitch/)[0]).toHaveTextContent("d16"); // 7.0 µA
  });
});
