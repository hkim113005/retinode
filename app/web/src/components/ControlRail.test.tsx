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
});
