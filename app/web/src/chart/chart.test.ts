import { describe, expect, it } from "vitest";
import type { CompareResponse, StudyPoint } from "../api/client";
import { fieldScene } from "./plots/field";
import { paretoGeom, paretoScene } from "./plots/pareto";
import type { Circle, Scene, Text } from "./scene";
import { PAPER, withAlpha } from "./scene";
import { toSvg } from "./svg";

const DATA: CompareResponse = {
  field: {
    xs_um: [-100, 0, 100],
    ys_um: [-100, 0, 100],
    // row-major over ys then xs; the centre is the strong negative well
    ve_mV: [
      [0, -0.5, 0],
      [-0.5, -2, -0.5],
      [0, -0.5, 0],
    ],
    vmax_mV: 2,
  },
  electrodes: [{ x_um: 0, y_um: 0, radius_um: 5 }],
  cells: [
    { x_um: 0, y_um: 0, is_target: true },
    { x_um: 40, y_um: 0, is_target: false },
  ],
  scorecard: null,
};

const P = (d: number, pitch: number, cost: number, sel: number, safe = true, front = true) =>
  ({
    diameter_um: d,
    pitch_um: pitch,
    cost_uA: cost,
    selectivity_uA: sel,
    safe,
    on_frontier: front,
  }) as StudyPoint;

const circles = (s: Scene) => s.items.filter((i): i is Circle => i.kind === "circle");
const texts = (s: Scene) => s.items.filter((i): i is Text => i.kind === "text");

describe("withAlpha", () => {
  it("expands shorthand hex and passes functional colours through", () => {
    expect(withAlpha("#08f", 0.5)).toBe("rgba(0, 136, 255, 0.5)");
    expect(withAlpha("rgba(1, 2, 3, 1)", 0.5)).toBe("rgba(1, 2, 3, 1)");
  });
});

describe("fieldScene", () => {
  it("skips near-zero cells and colours by sign", () => {
    const s = fieldScene({ data: DATA, size: 300, palette: PAPER });
    const rects = s.items.filter((i) => i.kind === "rect");
    // the four corners are exactly zero — they must not be painted at all
    expect(rects).toHaveLength(5);
    // every painted cell here is negative, so all of them wear the potential blue
    expect(rects.every((r) => r.fill?.startsWith("rgba(10, 106, 224"))).toBe(true);
  });

  it("draws the target filled and the off-target hollow", () => {
    const s = fieldScene({ data: DATA, size: 300, palette: PAPER });
    const cells = circles(s).slice(-2); // electrodes are pushed first
    expect(cells[0].fill).toBe(PAPER.field); // target: filled
    expect(cells[1].fill).toBeUndefined(); // off-target: hollow, stroke only
    expect(cells[1].stroke).toBeTruthy();
  });

  it("draws a partial field rather than throwing when the grid is ragged", () => {
    // a malformed payload must not white-screen the app: draw what is there
    const ragged: CompareResponse = {
      ...DATA,
      field: { ...DATA.field, ve_mV: [[-2, -3]] },
    };
    const s = fieldScene({ data: ragged, size: 300, palette: PAPER });
    expect(s.items.filter((i) => i.kind === "rect")).toHaveLength(2);
  });

  it("carries a round-numbered scale bar so the figure can be measured", () => {
    // extent is 100 µm, so half is 100 → the largest round length under it is 50
    const s = fieldScene({ data: DATA, size: 300, palette: PAPER });
    expect(texts(s).map((t) => t.text)).toContain("50 µm");
    // and the bar is drawn to match the label: 50 of 200 µm across 300 px
    const bar = s.items.find((i) => i.kind === "path");
    expect(bar && bar.kind === "path" && bar.pts[1][0] - bar.pts[0][0]).toBeCloseTo(75);
  });

  it("titles itself with the tier and colour limit, and is opaque only for export", () => {
    expect(fieldScene({ data: DATA, size: 300, palette: PAPER }).background).toBeUndefined();
    const fig = fieldScene({ data: DATA, size: 300, palette: PAPER, inked: true, background: true });
    expect(fig.background).toBe("#ffffff");
    expect(fig.title).toContain("FEM");
    expect(fig.title).toContain("2.00 mV");
  });
});

describe("paretoScene", () => {
  const POINTS = [P(12, 40, 9, 11), P(16, 40, 7, 6), P(8, 55, 12, 4, false), P(20, 70, 8, 5, true, false)];

  it("says what to do when there is nothing to plot", () => {
    const s = paretoScene({ points: [], width: 600, height: 360, palette: PAPER });
    expect(texts(s).map((t) => t.text)).toContain("Run the study to fill the frontier");
    expect(circles(s)).toHaveLength(0);
  });

  it("draws every point, ringing the selection and hollowing the unsafe", () => {
    const s = paretoScene({
      points: POINTS,
      selected: POINTS[0],
      width: 600,
      height: 360,
      palette: PAPER,
    });
    const cs = circles(s);
    // 4 points + 1 halo behind the selected one
    expect(cs).toHaveLength(5);
    // the charge-unsafe design is stroked, never filled — it is not selectable
    const unsafe = cs.find((c) => c.stroke?.includes("201, 42, 47"));
    expect(unsafe?.fill).toBeUndefined();
    // the selected point wears the amber
    expect(cs.some((c) => c.fill === PAPER.warm)).toBe(true);
  });

  it("connects only the safe frontier designs, in cost order", () => {
    const s = paretoScene({ points: POINTS, width: 600, height: 360, palette: PAPER });
    const path = s.items.find((i) => i.kind === "path" && i.lineWidth === 2.5);
    expect(path).toBeDefined();
    // the two safe frontier points (cost 7 and 9) — the unsafe and dominated are out
    expect(path && path.kind === "path" && path.pts).toHaveLength(2);
    const g = paretoGeom(POINTS, 600, 360)!;
    // ordered by cost: the cheaper design comes first
    expect(path && path.kind === "path" && path.pts[0][0]).toBeCloseTo(g.x(POINTS[1]));
  });

  it("ticks both axes with readable numbers spanning the domain", () => {
    const s = paretoScene({ points: POINTS, width: 600, height: 360, palette: PAPER });
    const labels = texts(s).map((t) => t.text);
    const g = paretoGeom(POINTS, 600, 360)!;
    // costs run 7..12, so the domain is 6..13 — one decimal at that span
    expect(g.x0).toBeCloseTo(6);
    expect(g.x1).toBeCloseTo(13);
    expect(labels).toContain("6.0"); // the x domain's ends are both labelled
    expect(labels).toContain("13.0");
    expect(labels).toContain("0.0"); // y starts at zero
    expect(labels).toContain("12.0"); // and tops out just above the best window
  });

  it("maps a more selective, cheaper design up and to the left", () => {
    const g = paretoGeom(POINTS, 600, 360)!;
    expect(g.x(P(1, 1, 7, 6))).toBeLessThan(g.x(P(1, 1, 12, 6)));
    expect(g.y(P(1, 1, 7, 11))).toBeLessThan(g.y(P(1, 1, 7, 4))); // y grows downward
  });
});

describe("toSvg", () => {
  it("emits a standalone document carrying the scene's marks", () => {
    const svg = toSvg(fieldScene({ data: DATA, size: 300, palette: PAPER, background: true }));
    expect(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"')).toBe(true);
    expect(svg).toContain('viewBox="0 0 300 300"');
    expect(svg).toContain("<title>");
    expect(svg).toContain("<circle");
    expect(svg).toContain("<rect");
    // no CSS variables may survive into the file — they mean nothing outside the app
    expect(svg).not.toContain("var(--");
  });

  it("escapes text so a stray angle bracket cannot break the document", () => {
    const svg = toSvg({
      width: 10,
      height: 10,
      title: 'a & b <c> "d"',
      items: [{ kind: "text", x: 1, y: 2, text: "<script>x</script>" }],
    });
    expect(svg).toContain("&lt;script&gt;x&lt;/script&gt;");
    expect(svg).toContain("a &amp; b &lt;c&gt; &quot;d&quot;");
    expect(svg).not.toContain("<script>");
  });

  it("writes paths with a move then lines, closing only when asked", () => {
    const svg = toSvg({
      width: 10,
      height: 10,
      items: [
        {
          kind: "path",
          pts: [
            [0, 0],
            [5, 5],
          ],
          stroke: "#000",
          closed: true,
        },
      ],
    });
    expect(svg).toContain('d="M0 0 L5 5 Z"');
  });
});
