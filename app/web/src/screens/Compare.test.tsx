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
  field: {
    xs_um: [-1, 0, 1],
    ys_um: [-1, 0, 1],
    // (n, n) as the contract requires: a ragged grid is not a thing the API emits
    ve_mV: [
      [-1, -2, -1],
      [-2, -3, -2],
      [-1, -2, -1],
    ],
    vmax_mV: 3,
  },
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

  it("clears a running job's progress when a control is edited, so nothing locks", async () => {
    // regression: editing a control mid-job used to orphan the progress state (the
    // job's ticket goes stale so its own `.finally` declines to clear it), leaving
    // the Run action gone forever. The [controls] effect must clear it.
    vi.mocked(client.getJob).mockResolvedValue(RUNNING); // the job never finishes
    render(<Compare />);
    fireEvent.click(await screen.findByRole("button", { name: /Run scorecard/ }));
    // it is running now: the Run button is replaced by the progress bar
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /Run scorecard/ })).not.toBeInTheDocument(),
    );
    // edit a control -> the debounced field effect clears the orphaned progress
    fireEvent.input(screen.getByLabelText(/Electrode diameter/), { target: { value: "16" } });
    // the Run action returns rather than staying locked
    expect(await screen.findByRole("button", { name: /Run scorecard/ })).toBeInTheDocument();
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

  it("replaces the analytical field with an honest FEM-required prompt for a 3D body", async () => {
    render(<Compare />);
    await screen.findByLabelText(/potential field/i); // flat disk shows the analytical field
    // author a pillar
    fireEvent.click(screen.getByRole("tab", { name: "Pillar" }));
    // the misleading analytical field is gone; the honest prompt takes its place
    await waitFor(() =>
      expect(screen.queryByLabelText(/potential field/i)).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/can’t represent electrode geometry/i)).toBeInTheDocument();
    expect(screen.getByText(/3D · FEM required/)).toBeInTheDocument();
    // the scorecard request carries the body + overlap policy
    fireEvent.click(screen.getByRole("button", { name: /Run scorecard/ }));
    await waitFor(() =>
      expect(client.postScore).toHaveBeenCalledWith(
        expect.objectContaining({
          body: expect.objectContaining({ kind: "cylinder" }),
          overlap_policy: "reject",
        }),
      ),
    );
  });

  it("shows the FEM field once solved for a 3D body (holes and all)", async () => {
    vi.mocked(client.getJob).mockResolvedValue(FEM_DONE);
    render(<Compare />);
    fireEvent.click(await screen.findByRole("tab", { name: "Dome" }));
    fireEvent.click(await screen.findByRole("button", { name: /Run field \(FEM\)/ }));
    expect(await screen.findByText(/FEM ✓ inked/)).toBeInTheDocument();
    expect(screen.getByLabelText(/potential field/i)).toBeInTheDocument();
  });
});
