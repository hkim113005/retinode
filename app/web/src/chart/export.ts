// Figure export (P7 S7 / D8). Both formats serialise the SAME Scene the screen
// drew, so an exported figure is never a second, drifting implementation of the
// plot. SVG is the vector interchange format (Illustrator/Inkscape → PDF/EPS with
// no rasterisation); PNG is rendered at a caller-chosen device-pixel-ratio for
// slides and manuscripts that want pixels.
import { drawScene } from "./render";
import type { Scene } from "./scene";
import { toSvg } from "./svg";

/** Hand `blob` to the browser as a download named `filename`. */
export function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Download `text` as a file: the shared path for JSON/CSV/SVG. */
export function downloadText(filename: string, mime: string, text: string): void {
  downloadBlob(filename, new Blob([text], { type: mime }));
}

/** Export `scene` as a standalone vector SVG. */
export function exportSvg(scene: Scene, filename: string): void {
  downloadText(filename, "image/svg+xml", toSvg(scene));
}

/**
 * Export `scene` as a raster PNG at `scale`× device pixels (3× ≈ 300 dpi for a
 * figure printed at its on-screen size). Resolves once the file is handed off;
 * rejects if the canvas cannot encode.
 */
export async function exportPng(scene: Scene, filename: string, scale = 3): Promise<void> {
  const canvas = document.createElement("canvas");
  if (!drawScene(canvas, scene, scale)) throw new Error("this browser cannot render the figure");
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) throw new Error("could not encode the PNG");
  downloadBlob(filename, blob);
}
