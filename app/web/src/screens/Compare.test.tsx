import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { CompareResponse, JobStatus, Scorecard } from "../api/client";
import { Compare } from "./Compare";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    postCompare: vi.fn(),
    postScore: vi.fn(),
    postAccurateField: vi.fn(),
    getJob: vi.fn(),
  };
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

const SCORE: Scorecard = {
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

const RUNNING: JobStatus = {
  id: "j1",
  status: "running",
  fraction: 0.2,
  message: "queued",
  cached: false,
};
const DONE: JobStatus = {
  id: "j1",
  status: "done",
  fraction: 1,
  message: "done",
  cached: false,
  scorecard: SCORE,
};

const FEM_DONE: JobStatus = {
  id: "f1",
  status: "done",
  fraction: 1,
  message: "done",
  cached: false,
  field: { xs_um: [-1, 0, 1], ys_um: [-1, 0, 1], ve_mV: [[-2, -3, -2]], vmax_mV: 3 },
  max_divergence_pct: 21,
};

describe("Compare", () => {
  beforeEach(() => {
    vi.mocked(client.postCompare).mockResolvedValue(FIELD_ONLY);
    vi.mocked(client.postScore).mockResolvedValue(RUNNING);
    vi.mocked(client.postAccurateField).mockResolvedValue(RUNNING);
    vi.mocked(client.getJob).mockResolvedValue(DONE);
  });

  it("fetches the field live on mount, without requesting the scorecard", async () => {
    render(<Compare />);
    await waitFor(() => expect(client.postCompare).toHaveBeenCalled());
    expect(client.postCompare).toHaveBeenCalledWith(
      expect.objectContaining({ include_scorecard: false }),
      expect.anything(),
    );
    expect(screen.getByLabelText(/potential field/i)).toBeInTheDocument();
  });

  it("submits a scorecard job and polls it to the operating window", async () => {
    render(<Compare />);
    fireEvent.click(await screen.findByRole("button", { name: /Run scorecard/ }));
    expect(await screen.findByText("8.0 µA")).toBeInTheDocument();
    expect(client.postScore).toHaveBeenCalledTimes(1);
    expect(client.getJob).toHaveBeenCalledWith("j1"); // it polled the running job
  });

  it("renders immediately when the job is served from cache (no polling)", async () => {
    vi.mocked(client.postScore).mockResolvedValue({ ...DONE, cached: true });
    render(<Compare />);
    fireEvent.click(await screen.findByRole("button", { name: /Run scorecard/ }));
    expect(await screen.findByText("cached")).toBeInTheDocument();
    expect(client.getJob).not.toHaveBeenCalled();
  });

  it("runs the FEM field accurately and badges the tier with a divergence note", async () => {
    vi.mocked(client.getJob).mockResolvedValue(FEM_DONE);
    render(<Compare />);
    fireEvent.click(await screen.findByRole("button", { name: /Run accurately/ }));
    expect(await screen.findByText(/FEM ✓ inked/)).toBeInTheDocument();
    expect(screen.getByText(/differs from the analytical preview by up to 21%/)).toBeInTheDocument();
    expect(client.postAccurateField).toHaveBeenCalledWith(
      expect.objectContaining({ layout: "single" }),
    );
  });
});
