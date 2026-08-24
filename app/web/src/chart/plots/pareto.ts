// The Pareto plot: the selectivity-versus-cost decision surface. Dominated designs
// recede, the frontier is a lit curve, charge-unsafe designs are hollow red, the
// selected point is ringed (docs/phase-7-design.md). A pure Scene builder.
import type { StudyPoint } from "../../api/client";
import type { Item, Palette, Scene } from "../scene";
import { withAlpha } from "../scene";

export const PAD = { l: 56, r: 16, t: 18, b: 40 };

export type ParetoOpts = {
  points: StudyPoint[];
  selected?: StudyPoint | null;
  width: number;
  height: number;
  palette: Palette;
  background?: boolean;
  /** The in-progress brush rectangle, in plot pixels. Screen-only: it is a gesture,
   *  never part of an exported figure. */
  brush?: { l: number; r: number; t: number; b: number } | null;
};

/** Maps a point to plot pixels, and carries the domain so the axes can be ticked.
 *  Exported so hit-testing uses the same geometry the scene drew. A second copy
 *  would drift the click targets off the marks. */
export type ParetoGeom = {
  x: (p: StudyPoint) => number;
  y: (p: StudyPoint) => number;
  atCost: (cost: number) => number;
  atSel: (sel: number) => number;
  x0: number;
  x1: number;
  y1: number;
};

export function paretoGeom(points: StudyPoint[], width: number, height: number): ParetoGeom | null {
  if (points.length === 0) return null;
  const costs = points.map((p) => p.cost_uA);
  const sels = points.map((p) => p.selectivity_uA);
  const x0 = Math.min(...costs) - 1;
  const x1 = Math.max(...costs) + 1;
  const y1 = Math.max(...sels) + 1;
  const atCost = (c: number) => PAD.l + ((c - x0) / (x1 - x0 || 1)) * (width - PAD.l - PAD.r);
  const atSel = (s: number) => PAD.t + (1 - s / (y1 || 1)) * (height - PAD.t - PAD.b);
  return { x: (p) => atCost(p.cost_uA), y: (p) => atSel(p.selectivity_uA), atCost, atSel, x0, x1, y1 };
}

/** How many decimals a tick needs to stay distinguishable across `span`. */
function ticksFor(span: number): number {
  return span >= 20 ? 0 : span >= 4 ? 1 : 2;
}

const same = (a: StudyPoint, b: StudyPoint) =>
  a.diameter_um === b.diameter_um && a.pitch_um === b.pitch_um;

export function paretoScene({
  points,
  selected,
  width,
  height,
  palette,
  background,
  brush,
}: ParetoOpts): Scene {
  const items: Item[] = [];
  const bg = background ? palette.paper : undefined;

  if (points.length === 0) {
    items.push({
      kind: "text",
      x: width / 2,
      y: height / 2,
      text: "Run the study to fill the frontier",
      fill: withAlpha(palette.muted, 0.7),
      size: 13,
      family: palette.sans,
      anchor: "middle",
    });
    return { width, height, background: bg, title: "Pareto frontier (empty)", items };
  }

  const g = paretoGeom(points, width, height)!;

  // grid + numeric ticks. Colour carries the gestalt, but a reader cannot take a
  // magnitude off a gridline, so the digits are the truth (docs/phase-7-design.md).
  const xdp = ticksFor(g.x1 - g.x0);
  const ydp = ticksFor(g.y1);
  for (let i = 0; i <= 4; i++) {
    const gx = PAD.l + ((width - PAD.l - PAD.r) * i) / 4;
    const gy = PAD.t + ((height - PAD.t - PAD.b) * i) / 4;
    const xv = g.x0 + ((g.x1 - g.x0) * i) / 4;
    const yv = (g.y1 * (4 - i)) / 4;
    items.push(
      {
        kind: "path",
        pts: [
          [gx, PAD.t],
          [gx, height - PAD.b],
        ],
        stroke: withAlpha(palette.muted, 0.1),
        lineWidth: 1,
      },
      {
        kind: "path",
        pts: [
          [PAD.l, gy],
          [width - PAD.r, gy],
        ],
        stroke: withAlpha(palette.muted, 0.1),
        lineWidth: 1,
      },
      {
        kind: "text",
        x: gx,
        y: height - PAD.b + 14,
        text: xv.toFixed(xdp),
        fill: withAlpha(palette.muted, 0.85),
        size: 10,
        family: palette.mono,
        anchor: "middle",
      },
      {
        kind: "text",
        x: PAD.l - 8,
        y: gy + 3.5,
        text: yv.toFixed(ydp),
        fill: withAlpha(palette.muted, 0.85),
        size: 10,
        family: palette.mono,
        anchor: "end",
      },
    );
  }

  // axis labels
  items.push(
    {
      kind: "text",
      x: width / 2,
      y: height - 12,
      text: "µA to fire the target  →  more current",
      fill: withAlpha(palette.muted, 0.95),
      size: 11,
      family: palette.sans,
      anchor: "middle",
    },
    {
      kind: "text",
      x: 15,
      y: height / 2,
      text: "selective window (µA)  →  more selective",
      fill: withAlpha(palette.muted, 0.95),
      size: 11,
      family: palette.sans,
      anchor: "middle",
      rotate: -90,
    },
    {
      kind: "text",
      x: PAD.l + 6,
      y: PAD.t + 13,
      text: "◤ better",
      fill: withAlpha(palette.field, 0.6),
      size: 10,
      family: palette.mono,
    },
  );

  // the frontier, as a lit curve through the safe non-dominated designs
  const front = points.filter((p) => p.on_frontier && p.safe).sort((a, b) => a.cost_uA - b.cost_uA);
  if (front.length > 1) {
    items.push({
      kind: "path",
      pts: front.map((p) => [g.x(p), g.y(p)] as [number, number]),
      stroke: withAlpha(palette.field, 0.55),
      lineWidth: 2.5,
    });
  }

  for (const p of points) {
    const px = g.x(p);
    const py = g.y(p);
    if (!p.safe) {
      // over the charge limit: shown but hollow, so it is present and never selectable
      items.push({
        kind: "circle",
        cx: px,
        cy: py,
        r: 4,
        stroke: withAlpha(palette.alert, 0.75),
        lineWidth: 1.6,
      });
      continue;
    }
    const isSel = selected != null && same(p, selected);
    const r = p.on_frontier ? 5.5 : 3.6;
    if (isSel) {
      items.push({
        kind: "circle",
        cx: px,
        cy: py,
        r: r + 5,
        fill: withAlpha(palette.warm, 0.2),
      });
    }
    items.push({
      kind: "circle",
      cx: px,
      cy: py,
      r,
      fill: isSel ? palette.warm : p.on_frontier ? palette.field : withAlpha(palette.ink, 0.3),
    });
  }

  if (brush) {
    items.push({
      kind: "rect",
      x: brush.l,
      y: brush.t,
      w: brush.r - brush.l,
      h: brush.b - brush.t,
      fill: withAlpha(palette.warm, 0.1),
      stroke: withAlpha(palette.warm, 0.7),
      lineWidth: 1,
    });
  }

  return {
    width,
    height,
    background: bg,
    title: `Selectivity versus cost: ${points.length} geometries, ${front.length} on the frontier`,
    items,
  };
}
