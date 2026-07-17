// The Compare controls — the same handful the Dash app exposes. Edits the geometry
// and stimulus; the field recomputes live on the analytical tier.
export interface Controls {
  layout: "single" | "bipolar";
  electrode_um: number;
  pitch_um: number;
  phase_width_us: number;
  neighbor_um: number;
  sigma_S_per_m: number;
}

interface Slider {
  key: keyof Controls;
  label: string;
  min: number;
  max: number;
  step: number;
  unit: string;
  bipolarOnly?: boolean;
  decimals?: number;
}

// Ranges match the Dash app's, which are the ones the engine was exercised over —
// a narrower slider silently puts real configurations out of reach.
const SLIDERS: Slider[] = [
  { key: "electrode_um", label: "Electrode diameter", min: 5, max: 40, step: 1, unit: "µm" },
  { key: "pitch_um", label: "Pair pitch", min: 20, max: 160, step: 5, unit: "µm", bipolarOnly: true },
  { key: "neighbor_um", label: "Neighbour distance", min: 20, max: 160, step: 5, unit: "µm" },
  { key: "phase_width_us", label: "Phase width", min: 50, max: 500, step: 10, unit: "µs" },
  {
    key: "sigma_S_per_m",
    label: "Tissue conductivity",
    min: 0.2,
    max: 2.0,
    step: 0.1,
    unit: "S/m",
    decimals: 1,
  },
];

export function ControlRail({
  controls,
  onChange,
}: {
  controls: Controls;
  onChange: (next: Controls) => void;
}) {
  const set = (patch: Partial<Controls>) => onChange({ ...controls, ...patch });
  return (
    <div className="card panel">
      <h2>Configuration</h2>
      <div className="ctl">
        <label>
          Return<b>{controls.layout === "bipolar" ? "local" : "monopolar"}</b>
        </label>
        <div className="seg" role="tablist" aria-label="Electrode layout">
          {(["single", "bipolar"] as const).map((v) => (
            <button
              key={v}
              role="tab"
              aria-selected={controls.layout === v}
              className={controls.layout === v ? "on" : ""}
              onClick={() => set({ layout: v })}
            >
              {v === "single" ? "Monopolar" : "Bipolar"}
            </button>
          ))}
        </div>
      </div>
      {/* the pitch only means anything with a return electrode to be pitched from,
          so it is hidden rather than shown doing nothing */}
      {SLIDERS.filter((s) => !s.bipolarOnly || controls.layout === "bipolar").map((s) => (
        <div className="ctl" key={s.key}>
          <label htmlFor={`c-${s.key}`}>
            {s.label}
            <b>
              {s.decimals ? (controls[s.key] as number).toFixed(s.decimals) : controls[s.key]}{" "}
              {s.unit}
            </b>
          </label>
          <input
            id={`c-${s.key}`}
            type="range"
            min={s.min}
            max={s.max}
            step={s.step}
            value={controls[s.key] as number}
            onChange={(e) => set({ [s.key]: Number(e.target.value) } as Partial<Controls>)}
          />
        </div>
      ))}
    </div>
  );
}
