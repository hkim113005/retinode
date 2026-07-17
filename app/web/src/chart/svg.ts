// The SVG renderer: serialises a Scene to a standalone .svg document. This is the
// vector half of figure-quality export (P7 S7 / D8) — the output opens in
// Illustrator or Inkscape with every mark still an editable object, and converts to
// PDF/EPS from there without a rasterisation step.
import type { Item, Scene } from "./scene";

const esc = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// SVG carries far more precision than a figure needs; trimming it keeps the file
// small and diffable.
const n = (v: number): string => String(Math.round(v * 100) / 100);

function paint(it: { fill?: string; stroke?: string; lineWidth?: number }): string {
  const parts = [`fill="${it.fill ?? "none"}"`];
  if (it.stroke) parts.push(`stroke="${it.stroke}"`, `stroke-width="${n(it.lineWidth ?? 1)}"`);
  return parts.join(" ");
}

function itemToSvg(it: Item): string {
  switch (it.kind) {
    case "rect":
      return `<rect x="${n(it.x)}" y="${n(it.y)}" width="${n(it.w)}" height="${n(it.h)}" ${paint(it)}/>`;
    case "circle":
      return `<circle cx="${n(it.cx)}" cy="${n(it.cy)}" r="${n(Math.max(0, it.r))}" ${paint(it)}/>`;
    case "path": {
      if (it.pts.length === 0) return "";
      const d =
        it.pts.map(([x, y], i) => `${i ? "L" : "M"}${n(x)} ${n(y)}`).join(" ") +
        (it.closed ? " Z" : "");
      const dash = it.dash?.length ? ` stroke-dasharray="${it.dash.join(",")}"` : "";
      const join = it.stroke ? ' stroke-linejoin="round" stroke-linecap="round"' : "";
      return `<path d="${d}" ${paint(it)}${dash}${join}/>`;
    }
    case "text": {
      const anchor = it.anchor === "start" ? "" : ` text-anchor="${it.anchor ?? "start"}"`;
      const rot = it.rotate ? ` transform="rotate(${n(it.rotate)} ${n(it.x)} ${n(it.y)})"` : "";
      const weight = it.weight ? ` font-weight="${it.weight}"` : "";
      return (
        `<text x="${n(it.x)}" y="${n(it.y)}" fill="${it.fill ?? "#000"}" ` +
        `font-family="${esc(it.family ?? "sans-serif")}" font-size="${n(it.size ?? 12)}"` +
        `${weight}${anchor}${rot}>${esc(it.text)}</text>`
      );
    }
  }
}

/** Serialise `scene` to a standalone SVG document. */
export function toSvg(scene: Scene): string {
  const bg = scene.background
    ? `<rect width="${n(scene.width)}" height="${n(scene.height)}" fill="${scene.background}"/>`
    : "";
  const title = scene.title ? `<title>${esc(scene.title)}</title>` : "";
  const body = scene.items.map(itemToSvg).filter(Boolean).join("\n  ");
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${n(scene.width)}" height="${n(scene.height)}" ` +
    `viewBox="0 0 ${n(scene.width)} ${n(scene.height)}">\n  ${title}${bg}\n  ${body}\n</svg>\n`
  );
}
