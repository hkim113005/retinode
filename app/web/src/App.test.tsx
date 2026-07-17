import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "./api/client";
import type { CompareResponse } from "./api/client";
import { App } from "./App";

vi.mock("./api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/client")>();
  return { ...actual, postCompare: vi.fn(), postStudy: vi.fn(), getJob: vi.fn() };
});

const FIELD: CompareResponse = {
  field: { xs_um: [-1, 0, 1], ys_um: [-1, 0, 1], ve_mV: [[-1, -2, -1]], vmax_mV: 2 },
  electrodes: [],
  cells: [],
  scorecard: null,
};

describe("App navigation", () => {
  beforeEach(() => vi.mocked(client.postCompare).mockResolvedValue(FIELD));

  it("navigates from Compare to Study via the rail", async () => {
    render(<App />);
    await waitFor(() => expect(client.postCompare).toHaveBeenCalled()); // Compare mounted
    fireEvent.click(screen.getByRole("button", { name: "Study" }));
    expect(screen.getByRole("heading", { name: /Study · diameter × pitch/ })).toBeInTheDocument();
  });
});
