import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { CompareResponse } from "../api/client";
import { Compare } from "./Compare";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, postCompare: vi.fn() };
});

const FIELD_ONLY: CompareResponse = {
  field: {
    xs_um: [-1, 0, 1],
    ys_um: [-1, 0, 1],
    ve_mV: [
      [-1, -2, -1],
      [-2, -3, -2],
      [-1, -2, -1],
    ],
    vmax_mV: 3,
  },
  electrodes: [{ x_um: 0, y_um: 0, radius_um: 5 }],
  cells: [{ x_um: 0, y_um: 0, is_target: true }],
  scorecard: null,
};

const SCORED: CompareResponse = {
  ...FIELD_ONLY,
  scorecard: {
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
  },
};

describe("Compare", () => {
  // argument-aware, so call order doesn't matter: the field path returns the field
  // only; the scorecard path returns the operating window.
  beforeEach(() =>
    vi.mocked(client.postCompare).mockImplementation(async (c) =>
      c?.include_scorecard ? SCORED : FIELD_ONLY,
    ),
  );

  it("fetches the field live on mount, without requesting the scorecard", async () => {
    render(<Compare />);
    await waitFor(() => expect(client.postCompare).toHaveBeenCalled());
    expect(client.postCompare).toHaveBeenCalledWith(
      expect.objectContaining({ include_scorecard: false }),
      expect.anything(),
    );
    expect(screen.getByLabelText(/potential field/i)).toBeInTheDocument();
  });

  it("runs the scorecard on demand and renders the operating window", async () => {
    render(<Compare />);
    fireEvent.click(await screen.findByRole("button", { name: /Run scorecard/ }));
    expect(await screen.findByText("8.0 µA")).toBeInTheDocument();
    expect(client.postCompare).toHaveBeenCalledWith(
      expect.objectContaining({ include_scorecard: true }),
    );
  });
});
