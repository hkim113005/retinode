import { describe, expect, it } from "vitest";
import { isoContours, niceLevels, sampleGrid } from "./contours";

// a 5×5 radial well centred on (0, 0): z = -(4 - r), so z = -4 at the centre
const AX = [-2, -1, 0, 1, 2];
const WELL = AX.map((y) => AX.map((x) => -(4 - Math.hypot(x, y))));

describe("isoContours", () => {
  it("stitches a single closed ring around a radial well", () => {
    // z = -2.5 is where r = 1.5, between grid nodes, so no corner sits on the level
    const rings = isoContours(AX, AX, WELL, -2.5);
    expect(rings).toHaveLength(1);
    const ring = rings[0];
    // stitched head-to-tail all the way round: the last vertex returns to the first
    expect(ring[0][0]).toBeCloseTo(ring[ring.length - 1][0]);
    expect(ring[0][1]).toBeCloseTo(ring[ring.length - 1][1]);
    // and every vertex lies on the r = 1.5 circle (linear interp on a coarse grid,
    // so allow the chord error)
    for (const [x, y] of ring) expect(Math.hypot(x, y)).toBeCloseTo(1.5, 0);
  });

  it("still traces a level that lands exactly on grid nodes", () => {
    // z = -3 passes through (±1, 0) and (0, ±1), the marching-squares degeneracy.
    // It may come out in pieces, but it must be drawable and on the r = 1 circle.
    const rings = isoContours(AX, AX, WELL, -3);
    expect(rings.length).toBeGreaterThan(0);
    for (const ring of rings) for (const [x, y] of ring) expect(Math.hypot(x, y)).toBeCloseTo(1, 1);
  });

  it("returns nothing when the level is outside the data", () => {
    expect(isoContours(AX, AX, WELL, -99)).toHaveLength(0);
    expect(isoContours(AX, AX, WELL, 99)).toHaveLength(0);
  });

  it("interpolates the crossing rather than snapping to grid lines", () => {
    // a plain ramp along x: z = x. The level 0.5 must land at x = 0.5 exactly.
    const xs = [0, 1];
    const ys = [0, 1];
    const ramp = [
      [0, 1],
      [0, 1],
    ];
    const [ring] = isoContours(xs, ys, ramp, 0.5);
    expect(ring.every(([x]) => Math.abs(x - 0.5) < 1e-9)).toBe(true);
  });

  it("survives a flat grid without dividing by zero", () => {
    const flat = [
      [2, 2],
      [2, 2],
    ];
    expect(isoContours([0, 1], [0, 1], flat, 2)).toEqual([]);
  });
});

describe("niceLevels", () => {
  it("picks round steps inside the range and skips the zero line", () => {
    // a monopolar cathode: about -8 mV at the electrode, ~0 far away
    expect(niceLevels(-7.96, 0)).toEqual([-6, -4, -2]);
  });

  it("scales to small and large ranges alike", () => {
    expect(niceLevels(0, 100)).toEqual([20, 40, 60, 80]);
    expect(niceLevels(-0.4, 0.4)).toEqual([-0.2, 0.2]);
  });

  it("gives nothing for a degenerate range", () => {
    expect(niceLevels(1, 1)).toEqual([]);
    expect(niceLevels(5, 2)).toEqual([]);
  });
});

describe("sampleGrid", () => {
  it("reads corners exactly and interpolates between them", () => {
    const xs = [0, 2];
    const ys = [0, 2];
    const z = [
      [0, 10],
      [20, 30],
    ];
    expect(sampleGrid(xs, ys, z, 0, 0)).toBeCloseTo(0);
    expect(sampleGrid(xs, ys, z, 2, 0)).toBeCloseTo(10);
    expect(sampleGrid(xs, ys, z, 0, 2)).toBeCloseTo(20);
    expect(sampleGrid(xs, ys, z, 1, 1)).toBeCloseTo(15); // the centre of all four
  });

  it("returns null outside the grid rather than a made-up number", () => {
    expect(sampleGrid(AX, AX, WELL, 99, 0)).toBeNull();
    expect(sampleGrid(AX, AX, WELL, 0, -99)).toBeNull();
  });
});
