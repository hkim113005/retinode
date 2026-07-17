// Isopotential contours by marching squares (P7 S7b). Colour gives the gestalt of a
// field; a contour carrying its own mV value is what lets a reader take a *number*
// off it (docs/phase-7-design.md). Pure grid maths — no canvas, no DOM.

export type Poly = Array<[number, number]>;

type Seg = [[number, number], [number, number]];

/** Linear crossing between two corner values, guarding the degenerate v0 == v1. */
function lerp(p0: number, p1: number, v0: number, v1: number, level: number): number {
  const dv = v1 - v0;
  if (Math.abs(dv) < 1e-12) return p0;
  return p0 + ((level - v0) / dv) * (p1 - p0);
}

// Which pair of cell edges each of the 16 corner-signature cases joins. Edges are
// A=bottom, B=right, C=top, D=left. Cases 5 and 10 are the saddles, resolved below
// by the centre value rather than picked arbitrarily.
const CASES: Record<number, Array<[number, number]>> = {
  1: [[3, 0]],
  2: [[0, 1]],
  3: [[3, 1]],
  4: [[1, 2]],
  6: [[0, 2]],
  7: [[3, 2]],
  8: [[2, 3]],
  9: [[2, 0]],
  11: [[2, 1]],
  12: [[1, 3]],
  13: [[1, 0]],
  14: [[0, 3]],
};

/**
 * Trace `level` through the scalar grid `z` (row-major over `ys` then `xs`),
 * returning polylines in data coordinates.
 */
export function isoContours(xs: number[], ys: number[], z: number[][], level: number): Poly[] {
  const segs: Seg[] = [];
  const rows = Math.min(ys.length, z.length);

  for (let i = 0; i + 1 < rows; i++) {
    const r0 = z[i];
    const r1 = z[i + 1];
    if (!r0 || !r1) continue;
    const cols = Math.min(xs.length, r0.length, r1.length);
    for (let j = 0; j + 1 < cols; j++) {
      const a = r0[j];
      const b = r0[j + 1];
      const c = r1[j + 1];
      const d = r1[j];
      const x0 = xs[j];
      const x1 = xs[j + 1];
      const y0 = ys[i];
      const y1 = ys[i + 1];

      let idx = 0;
      if (a > level) idx |= 1;
      if (b > level) idx |= 2;
      if (c > level) idx |= 4;
      if (d > level) idx |= 8;
      if (idx === 0 || idx === 15) continue;

      // the four possible edge crossings, in the A/B/C/D order the table uses
      const pts: Array<[number, number]> = [
        [lerp(x0, x1, a, b, level), y0], // A: bottom
        [x1, lerp(y0, y1, b, c, level)], // B: right
        [lerp(x0, x1, d, c, level), y1], // C: top
        [x0, lerp(y0, y1, a, d, level)], // D: left
      ];

      let joins = CASES[idx];
      if (idx === 5 || idx === 10) {
        // saddle: the centre decides which way the two branches connect, so the
        // contour follows the field instead of a coin flip
        const centre = (a + b + c + d) / 4;
        const inside = centre > level;
        joins =
          idx === 5
            ? inside
              ? [
                  [3, 2],
                  [1, 0],
                ]
              : [
                  [3, 0],
                  [1, 2],
                ]
            : inside
              ? [
                  [0, 1],
                  [2, 3],
                ]
              : [
                  [0, 3],
                  [2, 1],
                ];
      }
      for (const [s, e] of joins ?? []) segs.push([pts[s], pts[e]]);
    }
  }
  return joinSegments(segs);
}

// Segments come out of the grid unordered. Stitching them into polylines is what
// makes the contour a single stroked object — smooth joins on screen, one <path>
// per ring in the exported figure rather than hundreds of disjoint sticks.
function joinSegments(segs: Seg[]): Poly[] {
  const key = (p: [number, number]) => `${p[0].toFixed(4)},${p[1].toFixed(4)}`;
  const byStart = new Map<string, Seg[]>();
  for (const s of segs) {
    const k = key(s[0]);
    const list = byStart.get(k);
    list ? list.push(s) : byStart.set(k, [s]);
  }

  const used = new Set<Seg>();
  const out: Poly[] = [];
  for (const seed of segs) {
    if (used.has(seed)) continue;
    used.add(seed);
    const poly: Poly = [seed[0], seed[1]];
    // walk forward from the tail until the chain closes or runs out
    for (;;) {
      const next = (byStart.get(key(poly[poly.length - 1])) ?? []).find((s) => !used.has(s));
      if (!next) break;
      used.add(next);
      poly.push(next[1]);
      if (key(next[1]) === key(poly[0])) break; // closed ring
    }
    if (poly.length > 1) out.push(poly);
  }
  return out;
}

/**
 * Round contour levels spanning (`lo`, `hi`) — 1/2/5 × 10ⁿ steps, so a reader sees
 * "-4 mV" and not "-3.87 mV". Levels at or near zero are dropped: the zero
 * isopotential of a symmetric field is a meaningless line through everything.
 */
export function niceLevels(lo: number, hi: number, target = 4): number[] {
  const span = hi - lo;
  if (!(span > 0) || !Number.isFinite(span)) return [];
  // snap the ideal step up to the nearest 1/2/5 × 10ⁿ
  const raw = span / target;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const frac = raw / pow;
  const step = pow * (frac < 1.5 ? 1 : frac < 3 ? 2 : frac < 7 ? 5 : 10);
  const levels: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v < hi; v += step) {
    const level = Number(v.toFixed(6));
    // a level sitting on the data's own floor traces a point, not a ring; a level
    // at zero traces the whole symmetric plane. Neither is worth drawing.
    if (level > lo && Math.abs(level) > step * 0.5) levels.push(level);
  }
  return levels;
}

/** Bilinear sample of `z` at (x, y) in data coords; null outside the grid. */
export function sampleGrid(xs: number[], ys: number[], z: number[][], x: number, y: number): number | null {
  const j = span(xs, x);
  const i = span(ys, y);
  if (i == null || j == null) return null;
  const r0 = z[i.k];
  const r1 = z[i.k + 1];
  if (!r0 || !r1) return null;
  const top = r0[j.k] * (1 - j.t) + r0[j.k + 1] * j.t;
  const bot = r1[j.k] * (1 - j.t) + r1[j.k + 1] * j.t;
  return top * (1 - i.t) + bot * i.t;
}

/** The cell index and fractional offset of `v` within the ascending `axis`. */
function span(axis: number[], v: number): { k: number; t: number } | null {
  if (axis.length < 2 || v < axis[0] || v > axis[axis.length - 1]) return null;
  let k = 0;
  while (k + 2 < axis.length && axis[k + 1] < v) k++;
  const w = axis[k + 1] - axis[k];
  return { k, t: w === 0 ? 0 : (v - axis[k]) / w };
}
