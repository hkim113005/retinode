import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ControlRail } from "./ControlRail";
import type { Controls } from "./ControlRail";

const BASE: Controls = {
  layout: "single",
  electrode_um: 10,
  pitch_um: 60,
  phase_width_us: 200,
  neighbor_um: 40,
  sigma_S_per_m: 1,
};

describe("ControlRail", () => {
  it("emits a layout switch", () => {
    const onChange = vi.fn();
    render(<ControlRail controls={BASE} onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "Bipolar" }));
    expect(onChange).toHaveBeenCalledWith({ ...BASE, layout: "bipolar" });
  });

  it("emits a slider edit as a number", () => {
    const onChange = vi.fn();
    render(<ControlRail controls={BASE} onChange={onChange} />);
    // React range inputs fire onChange on the native `input` event, not `change`.
    fireEvent.input(screen.getByLabelText(/Electrode diameter/), { target: { value: "16" } });
    expect(onChange).toHaveBeenCalledWith({ ...BASE, electrode_um: 16 });
  });

  it("exposes tissue conductivity — it is a physics dimension, not a constant", () => {
    const onChange = vi.fn();
    render(<ControlRail controls={BASE} onChange={onChange} />);
    const sigma = screen.getByLabelText(/Tissue conductivity/);
    expect(sigma).toHaveAttribute("min", "0.2");
    expect(sigma).toHaveAttribute("max", "2");
    fireEvent.input(sigma, { target: { value: "1.4" } });
    expect(onChange).toHaveBeenCalledWith({ ...BASE, sigma_S_per_m: 1.4 });
  });

  it("keeps the engine's exercised ranges reachable", () => {
    render(<ControlRail controls={BASE} onChange={vi.fn()} />);
    expect(screen.getByLabelText(/Electrode diameter/)).toHaveAttribute("max", "40");
    expect(screen.getByLabelText(/Neighbour distance/)).toHaveAttribute("max", "160");
  });

  it("hides the pair pitch until there is a return electrode to pitch from", () => {
    const { rerender } = render(<ControlRail controls={BASE} onChange={vi.fn()} />);
    expect(screen.queryByLabelText(/Pair pitch/)).not.toBeInTheDocument();
    rerender(<ControlRail controls={{ ...BASE, layout: "bipolar" }} onChange={vi.fn()} />);
    expect(screen.getByLabelText(/Pair pitch/)).toBeInTheDocument();
  });
});
