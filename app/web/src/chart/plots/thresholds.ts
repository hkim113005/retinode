// The threshold plot: every cell's threshold on one current axis, with the safety
// ceiling and the selective window drawn over them. This is the scorecard's numbers
// laid out in the dimension they actually live in — µA — so "the window is 4 µA
// wide" stops being a figure to trust and becomes a distance you can see.
//
// Nothing here costs a NEURON run: the per-cell vector was already computed by the
// threshold search and was being collapsed to its minimum on the way out.
import type { Scorecard } from "../../api/client";
import type { Item, Palette, Scene } from "../scene";
import { withAlpha } from "../scene";

export const PAD = { l: 86, r: 20, t: 34, b: 40 };
const ROW = 22; // px per cell row

type Row = { id: string; uA: number; kind: "target" | "off" | "limiting" };

/** The rows a scorecard yields, target first then off-targets by threshold. */
export function thresholdRows(data: Scorecard): Row[] {
  if (!data.activated || data.target_uA == null) return [];
  const offs = Object.entries(data.off_target_thresholds_uA ?? {})
    .filter(([, uA]) => Number.isFinite(uA))
    .sort((a, b) => a[1] - b[1])
    .map(([id, uA]): Row => ({
      id,
      uA,
      kind: id === data.limiting_off_id ? "limiting" : "off",
    }));
  return [{ id: "target", uA: data.target_uA, kind: "target" }, ...offs];
}

export type ThresholdOpts = {
  data: Scorecard;
  width: number;
  palette: Palette;
  background?: boolean;
};

/** Height this plot needs for `data` — it grows with the cell count. */
export function thresholdHeight(data: Scorecard): number {
  return PAD.t + PAD.b + Math.max(1, thresholdRows(data).length) * ROW;
}

export function thresholdScene({ data, width, palette, background }: ThresholdOpts): Scene {
  const rows = thresholdRows(data);
  const height = thresholdHeight(data);
  const items: Item[] = [];
  const bg = background ? palette.paper : undefined;

  if (!rows.length) {
    items.push({
      kind: "text",
      x: width / 2,
      y: height / 2,
      text: "Run the scorecard to see where each cell fires",
      fill: withAlpha(palette.muted, 0.7),
      size: 12,
      family: palette.sans,
      anchor: "middle",
    });
    return { width, height, background: bg, title: "Thresholds (unscored)", items };
  }

  // The axis spans 0 to a little past whatever is furthest out — including the
  // ceiling, so a design whose safety limit sits inside its bystanders still shows
  // the ceiling rather than silently cropping it.
  const ceiling = data.safety_ceiling_uA;
  const far = Math.max(
    ...rows.map((r) => r.uA),
    ceiling != null && Number.isFinite(ceiling) ? ceiling : 0,
  );
  const hi = far * 1.12 || 1;
  const x = (uA: number) => PAD.l + (uA / hi) * (width - PAD.l - PAD.r);
  const yOf = (i: number) => PAD.t + i * ROW + ROW / 2;

  // the selective window, as a band from the target to whatever closes it
  const winHi = data.window_hi_uA;
  if (data.target_uA != null && winHi != null && Number.isFinite(winHi) && winHi > data.target_uA) {
    items.push({
      kind: "rect",
      x: x(data.target_uA),
      y: PAD.t - 8,
      w: x(winHi) - x(data.target_uA),
      h: rows.length * ROW + 8,
      fill: withAlpha(palette.ok, 0.11),
    });
    items.push({
      kind: "text",
      x: (x(data.target_uA) + x(winHi)) / 2,
      y: PAD.t - 14,
      text: "selective window",
      fill: withAlpha(palette.ok, 0.95),
      size: 10,
      family: palette.sans,
      anchor: "middle",
    });
  }

  // the safety ceiling: a hard wall, not a mark on a scale
  if (ceiling != null && Number.isFinite(ceiling) && ceiling <= hi) {
    items.push(
      {
        kind: "path",
        pts: [
          [x(ceiling), PAD.t - 8],
          [x(ceiling), height - PAD.b + 4],
        ],
        stroke: withAlpha(palette.alert, 0.8),
        lineWidth: 1.5,
        dash: [4, 3],
      },
      {
        kind: "text",
        x: x(ceiling),
        y: height - PAD.b + 16,
        text: `charge limit ${ceiling.toFixed(0)}`,
        fill: withAlpha(palette.alert, 0.95),
        size: 9.5,
        family: palette.mono,
        anchor: "middle",
      },
    );
  }

  rows.forEach((r, i) => {
    const y = yOf(i);
    const colour =
      r.kind === "target" ? palette.field : r.kind === "limiting" ? palette.warm : palette.ink;
    // a lollipop: the stem is "how much current it takes", the head is the threshold
    items.push(
      {
        kind: "path",
        pts: [
          [PAD.l, y],
          [x(r.uA), y],
        ],
        stroke: withAlpha(colour, 0.3),
        lineWidth: 1,
      },
      { kind: "circle", cx: x(r.uA), cy: y, r: r.kind === "target" ? 5 : 4, fill: colour },
      {
        kind: "text",
        x: PAD.l - 10,
        y: y + 3.5,
        text: r.id,
        fill: r.kind === "off" ? withAlpha(palette.muted, 0.95) : colour,
        size: 10.5,
        family: palette.mono,
        anchor: "end",
      },
      {
        kind: "text",
        x: x(r.uA) + 9,
        y: y + 3.5,
        text: r.uA.toFixed(1),
        fill: withAlpha(palette.ink, 0.75),
        size: 10,
        family: palette.mono,
      },
    );
  });

  items.push({
    kind: "text",
    x: width / 2,
    y: height - 6,
    text: "µA to fire  →",
    fill: withAlpha(palette.muted, 0.9),
    size: 10,
    family: palette.sans,
    anchor: "middle",
  });

  return {
    width,
    height,
    background: bg,
    title: `Thresholds: target ${data.target_uA?.toFixed(1)} µA, ${rows.length - 1} off-target${
      rows.length === 2 ? "" : "s"
    }`,
    items,
  };
}
