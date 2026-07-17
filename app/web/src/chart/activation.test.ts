import { describe, expect, it } from "vitest";
import type { AmplitudeSweep } from "../api/client";
import { activationScene } from "./plots/activation";
import type { Path, Scene, Text } from "./scene";
import { PAPER } from "./scene";

const SWEEP: AmplitudeSweep = {
  amplitudes_uA: [10, 20, 30, 40],
  curves: [
    {
      cell_id: "target",
      is_target: true,
      activated: [false, false, true, true],
      initiation_region: [null, null, "ais", "ais"],
      crossing_uA: 30,
      blocks: false,
    },
    {
      cell_id: "neighbor",
      is_target: false,
      activated: [false, true, true, false],
      initiation_region: [null, "soma", "soma", null],
      crossing_uA: 20,
      blocks: true,
    },
  ],
};

const texts = (s: Scene) => s.items.filter((i): i is Text => i.kind === "text").map((t) => t.text);
const paths = (s: Scene) => s.items.filter((i): i is Path => i.kind === "path");

describe("activationScene", () => {
  it("names every cell and marks the one that blocks", () => {
    const s = activationScene({ data: SWEEP, width: 600, palette: PAPER });
    const t = texts(s);
    expect(t).toContain("target");
    expect(t).toContain("neighbor");
    expect(t).toContain("blocks"); // depolarization block is called out, not smoothed
    expect(s.title).toContain("1 showing depolarization block");
  });

  it("steps the trace up where a cell fires and back down where it blocks", () => {
    const s = activationScene({ data: SWEEP, width: 600, palette: PAPER });
    // the widest path per lane is the trace; the neighbour's must end lower than
    // its middle, because it stopped firing again
    const trace = paths(s).find((p) => p.lineWidth === 1.4);
    expect(trace).toBeDefined();
    const ys = trace!.pts.map(([, y]) => y);
    expect(Math.min(...ys)).toBeLessThan(Math.max(...ys)); // it moved
    expect(ys[ys.length - 1]).toBe(Math.max(...ys)); // and came back down
  });

  it("draws the scorecard's threshold beside the grid's step, distinctly", () => {
    // the two numbers are different things — the bisection is accurate, the step is
    // grid resolution — so the plot shows both rather than picking one
    const s = activationScene({
      data: SWEEP,
      width: 600,
      palette: PAPER,
      targetThreshold_uA: 26.4,
    });
    expect(texts(s)).toContain("threshold 26.4");
    expect(paths(s).some((p) => p.dash)).toBe(true);
  });

  it("omits the threshold rule when it falls outside the swept range", () => {
    const s = activationScene({
      data: SWEEP,
      width: 600,
      palette: PAPER,
      targetThreshold_uA: 900, // never reached by this grid
    });
    expect(texts(s).some((t) => t.startsWith("threshold"))).toBe(false);
  });

  it("spaces the axis logarithmically so the threshold region is not squeezed away", () => {
    // thresholds cluster at the bottom of the range; on a linear axis a 1–200 µA
    // sweep buries them in the left margin. The geometric midpoint must land at the
    // middle of the plot, not at 100 µA's linear position.
    const wide: AmplitudeSweep = {
      amplitudes_uA: [1, 10, 100],
      curves: [
        {
          cell_id: "target",
          is_target: true,
          activated: [false, true, true],
          initiation_region: [null, "ais", "ais"],
          crossing_uA: 10,
          blocks: false,
        },
      ],
    };
    const s = activationScene({ data: wide, width: 600, palette: PAPER });
    const trace = paths(s).find((p) => p.lineWidth === 2)!;
    const xs = trace.pts.map(([px]) => px);
    const [first, last] = [Math.min(...xs), Math.max(...xs)];
    const mid = xs.find((v) => v > first && v < last)!;
    // 10 is the geometric middle of 1..100, so it sits ~halfway across
    expect((mid - first) / (last - first)).toBeCloseTo(0.5, 1);
  });

  it("says what to do when nothing has been swept", () => {
    const s = activationScene({
      data: { amplitudes_uA: [], curves: [] },
      width: 600,
      palette: PAPER,
    });
    expect(texts(s).some((t) => /Run the amplitude sweep/.test(t))).toBe(true);
  });
});
