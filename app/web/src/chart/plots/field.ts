// The field plot: the diverging Ve heatmap (blue negative / warm positive, centred
// on zero) with electrode footprints and soma markers overlaid. A pure Scene
// builder — see chart/scene.ts for why the plots live outside the components.
import type { CompareResponse } from "../../api/client";
import { isoContours, niceLevels } from "../contours";
import type { Item, Palette, Scene } from "../scene";
import { withAlpha } from "../scene";

export type FieldOpts = {
  data: CompareResponse;
  size: number; // square, in CSS px
  palette: Palette;
  inked?: boolean; // FEM results draw crisper (docs/phase-7-design.md)
  background?: boolean; // opaque paper — on for export, off on screen
  contours?: boolean; // labeled isopotential rings (default on)
};

/** Drop trailing zeros: contour labels read "-4 mV", never "-4.00 mV". */
function trim(v: number): string {
  return String(Number(v.toFixed(2)));
}

/** The largest round number (1/2/5 × 10ⁿ) that fits in `max` — scale-bar lengths a
 *  reader can do arithmetic with, rather than "43 µm". */
function niceLength(max: number): number {
  const pow = 10 ** Math.floor(Math.log10(Math.max(max, 1)));
  for (const m of [5, 2, 1]) if (m * pow <= max) return m * pow;
  return pow;
}

export function fieldScene({
  data,
  size,
  palette,
  inked,
  background,
  contours = true,
}: FieldOpts): Scene {
  const { xs_um, ys_um, ve_mV, vmax_mV } = data.field;
  const extent = xs_um[xs_um.length - 1] || 1;
  const toX = (x: number) => ((x + extent) / (2 * extent)) * size;
  const toY = (y: number) => ((extent - y) / (2 * extent)) * size;
  const items: Item[] = [];

  // heatmap: alpha ∝ |Ve| / vmax. Cells overlap slightly (1.06) so no seams show.
  // ve_mV is contracted to be (n, n) row-major over ys then xs, but we walk the
  // array's own bounds rather than assuming: a ragged payload should draw a partial
  // field, not throw and take the whole screen down with it.
  const dx = (size / (xs_um.length || 1)) * 1.06;
  const rows = Math.min(ys_um.length, ve_mV.length);
  for (let i = 0; i < rows; i++) {
    const row = ve_mV[i] ?? [];
    const cols = Math.min(xs_um.length, row.length);
    for (let j = 0; j < cols; j++) {
      const t = row[j] / (vmax_mV || 1);
      const a = Math.min(1, Math.abs(t));
      if (a < 0.02) continue; // near-zero cells would only muddy the paper
      items.push({
        kind: "rect",
        x: toX(xs_um[j]) - dx / 2,
        y: toY(ys_um[i]) - dx / 2,
        w: dx,
        h: dx,
        fill: withAlpha(t < 0 ? palette.field : palette.warm, a * (inked ? 1 : 0.85)),
      });
    }
  }

  // isopotential rings, each labelled with its own mV value at the ring's top. The
  // levels are round numbers and stack outward, so the labels never collide and the
  // reader can walk the gradient by number instead of by eye.
  if (contours) {
    let lo = Number.POSITIVE_INFINITY;
    let hi = Number.NEGATIVE_INFINITY;
    for (const row of ve_mV)
      for (const v of row) {
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    for (const level of niceLevels(lo, hi)) {
      const rings = isoContours(xs_um, ys_um, ve_mV, level);
      for (const ring of rings) {
        items.push({
          kind: "path",
          pts: ring.map(([x, y]) => [toX(x), toY(y)] as [number, number]),
          stroke: withAlpha(palette.ink, inked ? 0.45 : 0.3),
          lineWidth: 1,
        });
      }
      // label the biggest ring for this level, at its topmost point
      const main = rings.reduce<typeof rings[number] | null>(
        (best, r) => (best == null || r.length > best.length ? r : best),
        null,
      );
      if (!main) continue;
      const top = main.reduce((best, p) => (p[1] > best[1] ? p : best), main[0]);
      items.push({
        kind: "text",
        x: toX(top[0]),
        y: toY(top[1]) - 3,
        text: `${trim(level)} mV`,
        fill: withAlpha(palette.ink, 0.75),
        size: 9.5,
        family: palette.mono,
        anchor: "middle",
      });
    }
  }

  for (const e of data.electrodes) {
    items.push({
      kind: "circle",
      cx: toX(e.x_um),
      cy: toY(e.y_um),
      r: Math.max(3, (e.radius_um / (2 * extent)) * size),
      fill: withAlpha(palette.ink, 0.14),
      stroke: withAlpha(palette.ink, 0.6),
      lineWidth: 1.5,
    });
  }

  // cells: the target is filled and ringed, off-targets stay hollow
  for (const c of data.cells) {
    items.push(
      c.is_target
        ? {
            kind: "circle",
            cx: toX(c.x_um),
            cy: toY(c.y_um),
            r: 6,
            fill: palette.field,
            stroke: palette.paper,
            lineWidth: 1.5,
          }
        : {
            kind: "circle",
            cx: toX(c.x_um),
            cy: toY(c.y_um),
            r: 5,
            stroke: withAlpha(palette.ink, 0.6),
            lineWidth: 1.5,
          },
    );
  }

  // scale bar: a field figure with no scale cannot be measured, and the extent is
  // a control the reader never sees. Pick a round length under a quarter-width.
  const bar = niceLength(extent / 2);
  const px = (bar / (2 * extent)) * size;
  const x0 = size - px - 16;
  const yb = size - 18;
  items.push(
    {
      kind: "path",
      pts: [
        [x0, yb],
        [x0 + px, yb],
      ],
      stroke: palette.ink,
      lineWidth: 2,
    },
    {
      kind: "text",
      x: x0 + px / 2,
      y: yb - 6,
      text: `${bar} µm`,
      fill: palette.ink,
      size: 11,
      family: palette.mono,
      anchor: "middle",
    },
  );

  return {
    width: size,
    height: size,
    background: background ? palette.paper : undefined,
    title: `Extracellular potential (Ve), ±${vmax_mV.toFixed(2)} mV, ${
      inked ? "FEM" : "analytical"
    } tier`,
    items,
  };
}
