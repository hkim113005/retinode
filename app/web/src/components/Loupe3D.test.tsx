import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Loupe3D from "./Loupe3D";

// @react-three/fiber's Canvas is stubbed globally in src/test/setup.ts (no WebGL in
// jsdom), so this exercises the loupe's chrome — the corner ↔ expanded toggle.

const ELECTRODES = [{ x_um: 0, y_um: 0, radius_um: 5 }];
const CELLS = [{ x_um: 0, y_um: 0, is_target: true }];

describe("Loupe3D", () => {
  it("expands to a dialog and closes again", () => {
    render(<Loupe3D electrodes={ELECTRODES} cells={CELLS} />);
    const expand = screen.getByLabelText(/Expand the 3D array view/);
    expect(expand).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(expand);
    expect(screen.getByRole("dialog", { name: /Array in 3D/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  // The r3f Canvas is stubbed in jsdom (no WebGL), so the mesh itself is verified live
  // in the browser; here we only guard that a bodied marker flows through the props
  // without breaking the loupe's chrome.
  it("accepts a 3D-body marker (pillar) without breaking", () => {
    const pillar = [
      { x_um: 0, y_um: 0, radius_um: 5, body: { kind: "cylinder" as const, radius_um: 5, height_um: 30 } },
    ];
    render(<Loupe3D electrodes={pillar} cells={CELLS} />);
    expect(screen.getByLabelText(/Expand the 3D array view/)).toBeInTheDocument();
  });
});
