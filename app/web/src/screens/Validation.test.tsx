import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { ValidationReport } from "../api/client";
import { Validation } from "./Validation";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, getValidation: vi.fn() };
});

const REPORT: ValidationReport = {
  n_pass: 2,
  n_total: 3,
  reproductions: [
    {
      name: "the field is reciprocal",
      source: "quasi-static EM",
      passed: true,
      measured: "G(a,b) 2.12 vs G(b,a) 2.12",
      criterion: "reciprocal to 1e-9",
      note: "",
    },
    {
      name: "axon avoidance raises threshold",
      source: "Vilkhu 2021",
      passed: true,
      measured: "17 -> 373 µA",
      criterion: "> 5x",
      note: "",
    },
    {
      name: "somatic gain",
      source: "Fan 2019",
      passed: false,
      measured: "3.2x",
      criterion: "> 10x",
      note: "deferred to the FEM tier",
    },
  ],
};

describe("Validation", () => {
  beforeEach(() => vi.mocked(client.getValidation).mockResolvedValue(REPORT));

  it("shows the pass count and flags a failing reproduction honestly", async () => {
    render(<Validation />);
    // the headline count (the rail badge shows it too, hence the selector)
    expect(await screen.findByText("2/3", { selector: ".big" })).toBeInTheDocument();
    expect(screen.getByText("some failing")).toBeInTheDocument();
    expect(screen.getAllByText("pass")).toHaveLength(2);
    expect(screen.getByText("fail")).toBeInTheDocument();
  });

  it("renders each claim with its source, measurement and criterion", async () => {
    render(<Validation />);
    expect(await screen.findByText("the field is reciprocal")).toBeInTheDocument();
    expect(screen.getByText("Vilkhu 2021")).toBeInTheDocument();
    expect(screen.getByText("17 -> 373 µA")).toBeInTheDocument();
    expect(screen.getByText(/criterion: > 5x/)).toBeInTheDocument();
    expect(screen.getByText(/deferred to the FEM tier/)).toBeInTheDocument();
  });
});
