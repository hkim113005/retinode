// Activation versus amplitude: one trace per cell, showing where it fires.
//
// Deliberately NOT an "activation fraction" curve. The patch is a target plus its
// bystanders (a handful of cells), so a fraction would be a two-level step function
// dressed up as a sigmoid. Per-cell traces are what the engine actually knows, and a
// step IS the honest shape of "this cell fires above 26 µA".
import type { AmplitudeSweep } from "../../api/client";
import type { Item, Palette, Scene } from "../scene";
import { withAlpha } from "../scene";

export const PAD = { l: 76, r: 18, t: 26, b: 42 };
const LANE = 26; // px per cell trace

export type ActivationOpts = {
  data: AmplitudeSweep;
  width: number;
  palette: Palette;
  /** The scorecard's bisected threshold, drawn as a rule. It is the accurate number;
   *  the trace's step is only as fine as the grid, and showing both makes the
   *  difference visible instead of arguable. */
  targetThreshold_uA?: number | null;
  background?: boolean;
};

export function activationHeight(data: AmplitudeSweep): number {
  return PAD.t + PAD.b + Math.max(1, data.curves.length) * LANE;
}

export function activationScene({
  data,
  width,
  palette,
  targetThreshold_uA,
  background,
}: ActivationOpts): Scene {
  const amps = data.amplitudes_uA;
  const height = activationHeight(data);
  const items: Item[] = [];
  const bg = background ? palette.paper : undefined;

  if (!amps.length || !data.curves.length) {
    items.push({
      kind: "text",
      x: width / 2,
      y: height / 2,
      text: "Run the amplitude sweep to see who fires",
      fill: withAlpha(palette.muted, 0.7),
      size: 12,
      family: palette.sans,
      anchor: "middle",
    });
    return { width, height, background: bg, title: "Activation (unswept)", items };
  }

  const lo = amps[0];
  const hi = amps[amps.length - 1];
  // A LOG axis. Amplitude is positive and spans a decade or more, and thresholds
  // cluster at the bottom of it. On a linear axis the whole interesting region is
  // squeezed into the left margin while the flat top eats the plot. Falls back to
  // linear only for a non-positive range, which the API forbids anyway.
  const logAxis = lo > 0 && hi > lo;
  const t = (uA: number) =>
    logAxis
      ? (Math.log(Math.max(uA, lo)) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))
      : (uA - lo) / (hi - lo || 1);
  const x = (uA: number) => PAD.l + t(uA) * (width - PAD.l - PAD.r);
  const laneY = (i: number) => PAD.t + i * LANE + LANE / 2;

  // amplitude axis. Ticks are placed evenly on screen, so on a log axis they carry
  // round-ish values from the geometric progression rather than a linear one
  for (let i = 0; i <= 4; i++) {
    const f = i / 4;
    const v = logAxis
      ? Math.exp(Math.log(lo) + (Math.log(hi) - Math.log(lo)) * f)
      : lo + (hi - lo) * f;
    items.push(
      {
        kind: "path",
        pts: [
          [x(v), PAD.t - 6],
          [x(v), height - PAD.b + 2],
        ],
        stroke: withAlpha(palette.muted, 0.1),
        lineWidth: 1,
      },
      {
        kind: "text",
        x: x(v),
        y: height - PAD.b + 16,
        text: v.toFixed(0),
        fill: withAlpha(palette.muted, 0.85),
        size: 10,
        family: palette.mono,
        anchor: "middle",
      },
    );
  }

  // the scorecard's threshold, for comparison against the grid's step
  if (targetThreshold_uA != null && Number.isFinite(targetThreshold_uA)) {
    const tx = x(targetThreshold_uA);
    if (tx >= PAD.l && tx <= width - PAD.r) {
      items.push(
        {
          kind: "path",
          pts: [
            [tx, PAD.t - 6],
            [tx, height - PAD.b + 2],
          ],
          stroke: withAlpha(palette.field, 0.7),
          lineWidth: 1.5,
          dash: [3, 3],
        },
        {
          kind: "text",
          x: tx,
          y: PAD.t - 12,
          text: `threshold ${targetThreshold_uA.toFixed(1)}`,
          fill: withAlpha(palette.field, 0.95),
          size: 9.5,
          family: palette.mono,
          anchor: "middle",
        },
      );
    }
  }

  data.curves.forEach((c, i) => {
    const y = laneY(i);
    const colour = c.is_target ? palette.field : palette.ink;

    // the lane: a faint rule the trace steps up from
    items.push({
      kind: "path",
      pts: [
        [PAD.l, y],
        [width - PAD.r, y],
      ],
      stroke: withAlpha(palette.muted, 0.12),
      lineWidth: 1,
    });

    // the trace: a step per grid point. Firing lifts it; a block drops it again,
    // which is the whole reason to keep the curve rather than just its crossing.
    const pts: Array<[number, number]> = [];
    c.activated.forEach((on, j) => {
      const px = x(amps[j]);
      const py = y + (on ? -7 : 4);
      if (pts.length) pts.push([px, pts[pts.length - 1][1]]); // square corner
      pts.push([px, py]);
    });
    items.push({
      kind: "path",
      pts,
      stroke: withAlpha(colour, c.is_target ? 0.95 : 0.55),
      lineWidth: c.is_target ? 2 : 1.4,
    });

    items.push({
      kind: "text",
      x: PAD.l - 10,
      y: y + 3.5,
      text: c.cell_id,
      fill: c.is_target ? colour : withAlpha(palette.muted, 0.95),
      size: 10.5,
      family: palette.mono,
      anchor: "end",
    });

    if (c.blocks) {
      items.push({
        kind: "text",
        x: width - PAD.r,
        y: y + 3.5,
        text: "blocks",
        fill: withAlpha(palette.alert, 0.95),
        size: 9.5,
        family: palette.mono,
        anchor: "end",
      });
    }
  });

  items.push({
    kind: "text",
    x: width / 2,
    y: height - 6,
    text: "µA  →   (step up = fires)",
    fill: withAlpha(palette.muted, 0.9),
    size: 10,
    family: palette.sans,
    anchor: "middle",
  });

  const blockers = data.curves.filter((c) => c.blocks).length;
  return {
    width,
    height,
    background: bg,
    title: `Activation vs amplitude: ${data.curves.length} cells over ${amps.length} amplitudes${
      blockers ? `, ${blockers} showing depolarization block` : ""
    }`,
    items,
  };
}
