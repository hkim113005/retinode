import { describe, expect, it } from "vitest";
import type { Scorecard } from "../api/client";
import { thresholdRows, thresholdScene } from "./plots/thresholds";
import type { Circle, Scene, Text } from "./scene";
import { PAPER } from "./scene";

const CARD: Scorecard = {
  activated: true,
  target_uA: 8,
  off_min_uA: 12,
  ratio: 1.5,
  window_lo_uA: 8,
  window_hi_uA: 12,
  usable_margin_uA: 4,
  usable: true,
  limiting: "off_target",
  safety_ceiling_uA: 30,
  safe_at_target: true,
  off_target_thresholds_uA: { far: 26, near: 12 },
  limiting_off_id: "near",
};

const texts = (s: Scene) => s.items.filter((i): i is Text => i.kind === "text").map((t) => t.text);
const circles = (s: Scene) => s.items.filter((i): i is Circle => i.kind === "circle");

describe("thresholdRows", () => {
  it("puts the target first, then off-targets nearest-first", () => {
    expect(thresholdRows(CARD).map((r) => r.id)).toEqual(["target", "near", "far"]);
  });

  it("marks the cell that binds the window", () => {
    expect(thresholdRows(CARD).map((r) => r.kind)).toEqual(["target", "limiting", "off"]);
  });

  it("has nothing to show when the target never fired", () => {
    expect(thresholdRows({ activated: false })).toEqual([]);
  });

  it("drops off-targets that never fire rather than plotting them at infinity", () => {
    const rows = thresholdRows({
      ...CARD,
      off_target_thresholds_uA: { near: 12, never: Number.POSITIVE_INFINITY },
    });
    expect(rows.map((r) => r.id)).toEqual(["target", "near"]);
  });
});

describe("thresholdScene", () => {
  it("draws one mark per cell and labels each with its current", () => {
    const s = thresholdScene({ data: CARD, width: 600, palette: PAPER });
    expect(circles(s)).toHaveLength(3);
    const t = texts(s);
    expect(t).toContain("target");
    expect(t).toContain("near");
    expect(t).toContain("8.0");
    expect(t).toContain("12.0");
  });

  it("colours the target and the binding bystander distinctly from the rest", () => {
    const cs = circles(thresholdScene({ data: CARD, width: 600, palette: PAPER }));
    expect(cs[0].fill).toBe(PAPER.field); // target
    expect(cs[1].fill).toBe(PAPER.warm); // binds the window
    expect(cs[2].fill).toBe(PAPER.ink); // just another off-target
  });

  it("orders the marks by current along the axis", () => {
    const cs = circles(thresholdScene({ data: CARD, width: 600, palette: PAPER }));
    expect(cs[0].cx).toBeLessThan(cs[1].cx);
    expect(cs[1].cx).toBeLessThan(cs[2].cx);
  });

  it("draws the window band and the charge limit", () => {
    const s = thresholdScene({ data: CARD, width: 600, palette: PAPER });
    expect(texts(s)).toContain("selective window");
    expect(texts(s)).toContain("charge limit 30");
    const dashed = s.items.find((i) => i.kind === "path" && i.dash);
    expect(dashed).toBeDefined();
  });

  it("keeps a ceiling inside the bystanders on screen rather than cropping it", () => {
    // a design whose charge limit bites BEFORE any bystander fires: the axis must
    // still reach the ceiling, or the wall would vanish off the right edge
    const tight: Scorecard = { ...CARD, safety_ceiling_uA: 9, window_hi_uA: 9 };
    expect(texts(thresholdScene({ data: tight, width: 600, palette: PAPER }))).toContain(
      "charge limit 9",
    );
  });

  it("says what to do instead of drawing an empty axis", () => {
    const s = thresholdScene({ data: { activated: false }, width: 600, palette: PAPER });
    expect(texts(s).some((t) => /Run the scorecard/.test(t))).toBe(true);
    expect(circles(s)).toHaveLength(0);
  });
});
