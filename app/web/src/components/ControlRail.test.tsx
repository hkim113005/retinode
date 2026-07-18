import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  body: { kind: "none" },
  overlap_policy: "reject",
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

  it("switches the electrode to a 3D pillar with sensible starting dimensions", () => {
    const onChange = vi.fn();
    render(<ControlRail controls={BASE} onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "Pillar" }));
    expect(onChange).toHaveBeenCalledWith({
      ...BASE,
      body: { kind: "cylinder", radius_um: 5, height_um: 30, conductive_faces: "tip" },
    });
  });

  it("shows body dimensions + conductive faces only for a bodied electrode", () => {
    const flat = render(<ControlRail controls={BASE} onChange={vi.fn()} />);
    expect(screen.queryByLabelText(/Radius/)).not.toBeInTheDocument();
    expect(screen.queryByRole("tablist", { name: /Conductive faces/ })).not.toBeInTheDocument();
    flat.unmount();

    const cyl: Controls = {
      ...BASE,
      body: { kind: "cylinder", radius_um: 5, height_um: 30, conductive_faces: "tip" },
    };
    render(<ControlRail controls={cyl} onChange={vi.fn()} />);
    expect(screen.getByLabelText(/Radius/)).toHaveValue(5);
    expect(screen.getByLabelText(/Height/)).toHaveValue(30);
    expect(screen.getByRole("tablist", { name: /Conductive faces/ })).toBeInTheDocument();
  });

  it("edits a body dimension as a number", () => {
    const onChange = vi.fn();
    const cyl: Controls = {
      ...BASE,
      body: { kind: "cylinder", radius_um: 5, height_um: 30, conductive_faces: "tip" },
    };
    render(<ControlRail controls={cyl} onChange={onChange} />);
    fireEvent.input(screen.getByLabelText(/Height/), { target: { value: "15" } });
    expect(onChange).toHaveBeenCalledWith({
      ...cyl,
      body: { kind: "cylinder", radius_um: 5, height_um: 15, conductive_faces: "tip" },
    });
  });

  it("exposes the overlap policy only when a body can hit a cell", () => {
    const flat = render(<ControlRail controls={BASE} onChange={vi.fn()} />);
    expect(screen.queryByRole("tablist", { name: /Cell overlap/ })).not.toBeInTheDocument();
    flat.unmount();

    const onChange = vi.fn();
    const dome: Controls = { ...BASE, body: { kind: "hemisphere", radius_um: 10 } };
    render(<ControlRail controls={dome} onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "displace" }));
    expect(onChange).toHaveBeenCalledWith({ ...dome, overlap_policy: "displace" });
  });

  it("uploads a CAD solid and sets the body's upload id", async () => {
    const onChange = vi.fn();
    const uploadCad = vi.fn().mockResolvedValue({ upload_id: "abc123.step", filename: "pillar.step" });
    const cad: Controls = { ...BASE, body: { kind: "cad", upload_id: "", conductive_faces: "all" } };
    render(<ControlRail controls={cad} onChange={onChange} uploadCad={uploadCad} />);

    const file = new File([new Uint8Array([1, 2, 3])], "pillar.step");
    fireEvent.change(screen.getByLabelText(/CAD solid/), { target: { files: [file] } });
    await waitFor(() => expect(uploadCad).toHaveBeenCalledWith(file));
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({
        ...cad,
        body: { kind: "cad", upload_id: "abc123.step", conductive_faces: "all" },
      }),
    );
  });
});
