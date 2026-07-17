// The canvas renderer: paints a Scene onto a 2D context in CSS-pixel space. The
// caller owns the device-pixel-ratio transform, so the same code paints the screen
// (dpr 1–2) and a high-DPI export raster (dpr 3–4) with no special cases.
import type { Item, Scene } from "./scene";

function drawItem(ctx: CanvasRenderingContext2D, it: Item): void {
  switch (it.kind) {
    case "rect": {
      if (it.fill) {
        ctx.fillStyle = it.fill;
        ctx.fillRect(it.x, it.y, it.w, it.h);
      }
      if (it.stroke) {
        ctx.strokeStyle = it.stroke;
        ctx.lineWidth = it.lineWidth ?? 1;
        ctx.strokeRect(it.x, it.y, it.w, it.h);
      }
      return;
    }
    case "circle": {
      ctx.beginPath();
      ctx.arc(it.cx, it.cy, Math.max(0, it.r), 0, Math.PI * 2);
      if (it.fill) {
        ctx.fillStyle = it.fill;
        ctx.fill();
      }
      if (it.stroke) {
        ctx.strokeStyle = it.stroke;
        ctx.lineWidth = it.lineWidth ?? 1;
        ctx.stroke();
      }
      return;
    }
    case "path": {
      if (it.pts.length === 0) return;
      ctx.beginPath();
      it.pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      if (it.closed) ctx.closePath();
      if (it.fill) {
        ctx.fillStyle = it.fill;
        ctx.fill();
      }
      if (it.stroke) {
        ctx.strokeStyle = it.stroke;
        ctx.lineWidth = it.lineWidth ?? 1;
        ctx.setLineDash(it.dash ?? []);
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.stroke();
        ctx.setLineDash([]);
      }
      return;
    }
    case "text": {
      ctx.save();
      ctx.translate(it.x, it.y);
      if (it.rotate) ctx.rotate((it.rotate * Math.PI) / 180);
      ctx.fillStyle = it.fill ?? "#000";
      ctx.font = `${it.weight ?? 400} ${it.size ?? 12}px ${it.family ?? "sans-serif"}`;
      ctx.textAlign = it.anchor === "middle" ? "center" : (it.anchor ?? "start");
      ctx.textBaseline = "alphabetic";
      ctx.fillText(it.text, 0, 0);
      ctx.restore();
      return;
    }
  }
}

/**
 * Paint `scene` into `ctx`, scaled by `dpr`. Returns false when there is no usable
 * context (jsdom throws rather than returning null from getContext), so callers can
 * bail without a try/catch of their own.
 */
export function drawScene(canvas: HTMLCanvasElement, scene: Scene, dpr = 1): boolean {
  let ctx: CanvasRenderingContext2D | null = null;
  try {
    ctx = canvas.getContext("2d");
  } catch {
    return false;
  }
  if (!ctx) return false;

  canvas.width = Math.round(scene.width * dpr);
  canvas.height = Math.round(scene.height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, scene.width, scene.height);
  if (scene.background) {
    ctx.fillStyle = scene.background;
    ctx.fillRect(0, 0, scene.width, scene.height);
  }
  for (const it of scene.items) drawItem(ctx, it);
  return true;
}
