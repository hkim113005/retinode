import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { JobStatus } from "../api/client";
import { Study } from "./Study";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, postStudy: vi.fn(), getJob: vi.fn() };
});

const RUNNING: JobStatus = { id: "s1", status: "running", fraction: 0.3, message: "solving", cached: false };
const DONE: JobStatus = {
  id: "s1",
  status: "done",
  fraction: 1,
  message: "done",
  cached: false,
  study: {
    n_geometries: 3,
    tier: "fem" as const,
    points: [
      { diameter_um: 12, pitch_um: 40, cost_uA: 8, selectivity_uA: 9, safe: true, on_frontier: true },
      { diameter_um: 16, pitch_um: 40, cost_uA: 7, selectivity_uA: 6, safe: true, on_frontier: true },
      { diameter_um: 8, pitch_um: 55, cost_uA: 11, selectivity_uA: 5, safe: true, on_frontier: false },
    ],
  },
};

describe("Study", () => {
  beforeEach(() => {
    vi.mocked(client.postStudy).mockResolvedValue(RUNNING);
    vi.mocked(client.getJob).mockResolvedValue(DONE);
  });

  it("estimates the sweep size and drops nothing when all pitches exceed all diameters", () => {
    render(<Study />);
    // 4 diameters x 4 pitches, all pitches >= all diameters -> 16 combos
    expect(screen.getByText("16", { selector: ".cost .n" })).toBeInTheDocument();
  });

  it("shrinks the estimate when a diameter is removed", () => {
    render(<Study />);
    fireEvent.click(screen.getByRole("button", { name: "8" })); // deselect diameter 8
    expect(screen.getByText("12", { selector: ".cost .n" })).toBeInTheDocument();
  });

  it("runs the sweep and reports the frontier", async () => {
    render(<Study />);
    fireEvent.click(screen.getByRole("button", { name: /Run study/ }));
    expect(await screen.findByText(/3 geometries · 2 on the frontier/)).toBeInTheDocument();
    expect(client.postStudy).toHaveBeenCalledWith(
      expect.objectContaining({ diameters_um: [8, 12, 16, 20] }),
    );
  });
});
