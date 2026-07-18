// Repaint a canvas when its box changes size. The plot `useEffect`s key on data,
// so after a window resize the bitmap is still built at the old measured width and
// the marks blur/misalign until the next data change. A ResizeObserver bumps a
// counter the caller threads into its draw effect's deps, so a resize triggers a
// redraw at the new width. No-op where ResizeObserver is absent (jsdom).
import { useEffect, useState } from "react";

export function useResizeRedraw(ref: React.RefObject<HTMLElement | null>): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setTick((t) => t + 1));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return tick;
}
