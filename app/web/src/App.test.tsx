import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "./api/client";
import type { CompareResponse, JobStatus } from "./api/client";
import { App } from "./App";

vi.mock("./api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/client")>();
  return { ...actual, postCompare: vi.fn(), postStudy: vi.fn(), getJob: vi.fn() };
});

const FIELD: CompareResponse = {
  field: {
    xs_um: [-1, 0, 1],
    ys_um: [-1, 0, 1],
    // (n, n) as the contract requires
    ve_mV: [
      [-1, -2, -1],
      [-2, -3, -2],
      [-1, -2, -1],
    ],
    vmax_mV: 3,
  },
  electrodes: [],
  cells: [],
  scorecard: null,
};

const SWEPT: JobStatus = {
  id: "s1",
  status: "done",
  fraction: 1,
  message: "done",
  cached: false,
  study: {
    n_geometries: 3,
    tier: "fem" as const,
    points: [
      { diameter_um: 12, pitch_um: 40, cost_uA: 9, selectivity_uA: 11, safe: true, on_frontier: true },
      { diameter_um: 16, pitch_um: 40, cost_uA: 7, selectivity_uA: 6, safe: true, on_frontier: true },
      { diameter_um: 8, pitch_um: 55, cost_uA: 12, selectivity_uA: 4, safe: false, on_frontier: false },
    ],
  },
};

const W = 600;
const H = W * 0.6;

describe("App navigation", () => {
  beforeEach(() => {
    vi.mocked(client.postCompare).mockResolvedValue(FIELD);
    vi.mocked(client.postStudy).mockResolvedValue(SWEPT);
    // jsdom sizes every element at zero, which would collapse the Pareto geometry
    vi.spyOn(HTMLCanvasElement.prototype, "getBoundingClientRect").mockReturnValue({
      left: 0, top: 0, width: W, height: H, right: W, bottom: H, x: 0, y: 0, toJSON: () => ({}),
    });
  });

  it("navigates from Compare to Study via the rail", async () => {
    render(<App />);
    await waitFor(() => expect(client.postCompare).toHaveBeenCalled()); // Compare mounted
    fireEvent.click(screen.getByRole("button", { name: "Study" }));
    expect(screen.getByRole("heading", { name: /Study · diameter × pitch/ })).toBeInTheDocument();
  });

  it("carries a brushed subset of the sweep through to Candidates", async () => {
    render(<App />);
    await waitFor(() => expect(client.postCompare).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Study" }));
    fireEvent.click(screen.getByRole("button", { name: /Run study/ }));
    await screen.findByText(/3 geometries/);

    // brush the whole plot: both safe designs land in the box, the unsafe one cannot
    const canvas = screen.getByLabelText(/Pareto frontier/);
    fireEvent.mouseDown(canvas, { clientX: 0, clientY: 0 });
    fireEvent.mouseMove(canvas, { clientX: W, clientY: H });
    fireEvent.mouseUp(canvas, { clientX: W, clientY: H });
    expect(await screen.findByText(/Shortlist these 2/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Shortlist these 2/ }));
    // Candidates ranks the brush, and says that is what it did
    expect(screen.getByRole("heading", { name: /Candidates/ })).toBeInTheDocument();
    expect(screen.getByText("brushed from the study")).toBeInTheDocument();
    expect(screen.getByText(/2 charge-safe designs/)).toBeInTheDocument();

    // and the brush can be dropped to rank the whole sweep again
    fireEvent.click(screen.getByRole("button", { name: /Rank the whole sweep/ }));
    expect(screen.queryByText("brushed from the study")).not.toBeInTheDocument();
  });
});
