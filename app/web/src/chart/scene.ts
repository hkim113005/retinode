// The chart seam (P7 S7). A plot is a pure function from data to a `Scene` — a flat
// list of resolved primitives in CSS-pixel space. Two renderers consume it: canvas
// for the screen (fast, live) and SVG for export (vector, figure quality). Because
// both eat the same description, the exported figure IS what was on screen; it
// cannot drift. It also makes plots testable without a canvas.
//
// Colours are resolved to concrete strings when the scene is BUILT, never left as
// CSS variables — a var() reference means nothing inside a standalone .svg file.

export type Rect = {
  kind: "rect";
  x: number;
  y: number;
  w: number;
  h: number;
  fill?: string;
  stroke?: string;
  lineWidth?: number;
};

export type Circle = {
  kind: "circle";
  cx: number;
  cy: number;
  r: number;
  fill?: string;
  stroke?: string;
  lineWidth?: number;
};

export type Path = {
  kind: "path";
  pts: Array<[number, number]>;
  stroke?: string;
  fill?: string;
  lineWidth?: number;
  closed?: boolean;
  dash?: number[];
};

export type Text = {
  kind: "text";
  x: number;
  y: number;
  text: string;
  fill?: string;
  size?: number;
  family?: string;
  weight?: number;
  anchor?: "start" | "middle" | "end";
  rotate?: number; // degrees, about (x, y)
};

export type Item = Rect | Circle | Path | Text;

export type Scene = {
  width: number;
  height: number;
  background?: string; // opaque paper for export; omit for transparent
  title?: string; // becomes the SVG <title> — accessibility + figure provenance
  items: Item[];
};

/** The colours a plot draws with, resolved from the live theme or fixed for print. */
export type Palette = {
  field: string; // Ve potential (blue)
  warm: string; // activation / selection (amber)
  ok: string; // safe (green)
  alert: string; // over the limit (red)
  ink: string; // foreground marks
  muted: string; // axes, labels
  paper: string; // background
  sans: string;
  mono: string;
};

function cssVar(name: string, fallback: string): string {
  if (typeof getComputedStyle !== "function") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** The palette the app is currently wearing — so the screen matches the UI theme. */
export function livePalette(): Palette {
  return {
    field: cssVar("--field", "#007aff"),
    warm: cssVar("--warm", "#d1810b"),
    ok: cssVar("--ok", "#2fae5b"),
    alert: cssVar("--alert", "#e5484d"),
    ink: cssVar("--canvas-ink", "#1c1c1e"),
    muted: cssVar("--muted", "#6e6e73"),
    paper: cssVar("--surface", "#ffffff"),
    sans: cssVar("--sans", "system-ui, sans-serif"),
    mono: cssVar("--mono", "ui-monospace, Menlo, monospace"),
  };
}

/**
 * The print palette: dark ink on white, fixed regardless of the app's theme.
 *
 * A dark-mode PNG is useless in a paper, so "export exactly what I see" is the
 * wrong default for a figure. The export menu offers both; this is the one that
 * lands in a manuscript. Fonts are named generically so the SVG re-renders on a
 * machine that has never heard of this app.
 */
export const PAPER: Palette = {
  field: "#0a6ae0",
  warm: "#b96b00",
  ok: "#217a43",
  alert: "#c92a2f",
  ink: "#14161a",
  muted: "#5b6068",
  paper: "#ffffff",
  sans: "Helvetica, Arial, sans-serif",
  mono: "Menlo, Consolas, monospace",
};

/** `#rgb`/`#rrggbb` → `rgba(...)`. Passes through anything already functional. */
export function withAlpha(color: string, a: number): string {
  if (!color.startsWith("#")) return color;
  const h = color.slice(1);
  const f = h.length === 3
    ? h
        .split("")
        .map((c) => c + c)
        .join("")
    : h;
  const n = Number.parseInt(f, 16);
  if (Number.isNaN(n)) return color;
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${round(a)})`;
}

function round(v: number): number {
  return Math.round(v * 1000) / 1000;
}
