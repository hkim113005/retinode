import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StudyPoint } from "../api/client";
import { paretoGeom } from "../chart/plots/pareto";
import { ParetoPlot } from "./ParetoPlot";

const W = 600;
const H = W * 0.6;

const P = (d: number, pitch: number, cost: number, sel: number, safe = true, front = true) =>
  ({
    diameter_um: d,
    pitch_um: pitch,
    cost_uA: cost,
    selectivity_uA: sel,
    safe,
    on_frontier: front,
  }) as StudyPoint;

const CHEAP = P(16, 40, 7, 6);
const BEST = P(12, 40, 9, 11);
const UNSAFE = P(8, 55, 12, 4, false);
const POINTS = [CHEAP, BEST, UNSAFE];

const g = paretoGeom(POINTS, W, H)!;
const at = (p: StudyPoint) => ({ clientX: g.x(p), clientY: g.y(p) });

// jsdom gives every element a zero-sized box, which would collapse the plot's
// geometry and put every mark at the same place. Pin a real one.
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 0,
    width: W,
    height: H,
    right: W,
    bottom: H,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
});

const plot = (props: Partial<React.ComponentProps<typeof ParetoPlot>> = {}) => {
  const onSelect = vi.fn();
  const onBrush = vi.fn();
  render(
    <ParetoPlot points={POINTS} selected={null} onSelect={onSelect} onBrush={onBrush} {...props} />,
  );
  return { canvas: screen.getByLabelText(/Pareto frontier/), onSelect, onBrush };
};

describe("ParetoPlot hover", () => {
  it("reads out the design under the cursor", () => {
    const { canvas } = plot();
    fireEvent.mouseMove(canvas, at(BEST));
    expect(screen.getByRole("tooltip")).toHaveTextContent("d12 · pitch 40 µm");
    expect(screen.getByRole("tooltip")).toHaveTextContent("9.0 µA to fire");
    expect(screen.getByRole("tooltip")).toHaveTextContent("11.0 µA window");
    expect(screen.getByRole("tooltip")).toHaveTextContent("charge-safe");
  });

  it("says so when the design under the cursor is over the charge limit", () => {
    const { canvas } = plot();
    fireEvent.mouseMove(canvas, at(UNSAFE));
    expect(screen.getByRole("tooltip")).toHaveTextContent("over the charge limit");
  });

  it("shows nothing over empty space, and clears on leave", () => {
    const { canvas } = plot();
    fireEvent.mouseMove(canvas, { clientX: W - 5, clientY: H - 5 });
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.mouseMove(canvas, at(BEST));
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    fireEvent.mouseLeave(canvas);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});

describe("ParetoPlot selection", () => {
  it("treats a press-and-release on a mark as a click, not a brush", () => {
    const { canvas, onSelect, onBrush } = plot();
    fireEvent.mouseDown(canvas, at(BEST));
    fireEvent.mouseUp(canvas, at(BEST));
    expect(onSelect).toHaveBeenCalledWith(BEST);
    expect(onBrush).not.toHaveBeenCalled();
  });

  it("forgives a small wobble during a click", () => {
    const { canvas, onSelect, onBrush } = plot();
    const p = at(BEST);
    fireEvent.mouseDown(canvas, p);
    fireEvent.mouseMove(canvas, { clientX: p.clientX + 2, clientY: p.clientY + 1 });
    fireEvent.mouseUp(canvas, { clientX: p.clientX + 2, clientY: p.clientY + 1 });
    expect(onSelect).toHaveBeenCalledWith(BEST);
    expect(onBrush).not.toHaveBeenCalled();
  });
});

describe("ParetoPlot brush", () => {
  it("shortlists the safe designs inside the box and drops the unsafe one", () => {
    const { canvas, onBrush, onSelect } = plot();
    // a box over the whole plot: it covers all three, but UNSAFE must not survive
    fireEvent.mouseDown(canvas, { clientX: 0, clientY: 0 });
    fireEvent.mouseMove(canvas, { clientX: W, clientY: H });
    fireEvent.mouseUp(canvas, { clientX: W, clientY: H });
    expect(onBrush).toHaveBeenCalledWith(expect.arrayContaining([CHEAP, BEST]));
    expect(onBrush.mock.calls[0][0]).not.toContain(UNSAFE);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("brushes only what the box actually covers", () => {
    const { canvas, onBrush } = plot();
    const b = at(BEST);
    fireEvent.mouseDown(canvas, { clientX: b.clientX - 15, clientY: b.clientY - 15 });
    fireEvent.mouseMove(canvas, { clientX: b.clientX + 15, clientY: b.clientY + 15 });
    fireEvent.mouseUp(canvas, { clientX: b.clientX + 15, clientY: b.clientY + 15 });
    expect(onBrush).toHaveBeenCalledWith([BEST]);
  });

  it("does not fire an empty brush", () => {
    const { canvas, onBrush } = plot();
    // a box in a corner with nothing in it
    fireEvent.mouseDown(canvas, { clientX: W - 60, clientY: H - 60 });
    fireEvent.mouseMove(canvas, { clientX: W - 10, clientY: H - 10 });
    fireEvent.mouseUp(canvas, { clientX: W - 10, clientY: H - 10 });
    expect(onBrush).not.toHaveBeenCalled();
  });
});
