import { useState } from "react";

// The Compare controls: the same handful the Dash app exposes, plus an optional 3D
// electrode body. Edits the geometry and stimulus; a flat electrode recomputes live on
// the analytical tier, a body is FEM-only (the point source can't see geometry).
export type ConductiveFaces = "tip" | "sides" | "all";

// Mirrors api.models.BodySpec (discriminated on `kind`). A body shapes the driven
// electrode e0. CAD is authored via the upload picker (its `upload_id` comes back from
// POST /cad).
export type BodyControls =
  | { kind: "none" }
  | { kind: "hemisphere"; radius_um: number }
  | { kind: "cylinder"; radius_um: number; height_um: number; conductive_faces: ConductiveFaces }
  | {
      kind: "frustum";
      base_radius_um: number;
      top_radius_um: number;
      height_um: number;
      conductive_faces: ConductiveFaces;
    }
  | { kind: "cad"; upload_id: string; conductive_faces: ConductiveFaces };

export interface Controls {
  layout: "single" | "bipolar";
  electrode_um: number;
  pitch_um: number;
  phase_width_us: number;
  neighbor_um: number;
  sigma_S_per_m: number;
  body: BodyControls;
  overlap_policy: "reject" | "displace";
}

// Sensible starting dimensions when switching a body on, so the user sees a real shape
// rather than zeros. Keyed by kind; `none` clears the body.
const BODY_DEFAULTS: Record<BodyControls["kind"], BodyControls> = {
  none: { kind: "none" },
  hemisphere: { kind: "hemisphere", radius_um: 10 },
  cylinder: { kind: "cylinder", radius_um: 5, height_um: 30, conductive_faces: "tip" },
  frustum: {
    kind: "frustum",
    base_radius_um: 8,
    top_radius_um: 2,
    height_um: 20,
    conductive_faces: "tip",
  },
  cad: { kind: "cad", upload_id: "", conductive_faces: "all" },
};

// The numeric dimensions to show per body kind (µm). Rendered as number inputs: more
// precise than sliders for a design you're pinning down, and they stay out of the way
// for a flat electrode.
const BODY_DIMS: Record<Exclude<BodyControls["kind"], "none" | "cad">, readonly string[]> = {
  hemisphere: ["radius_um"],
  cylinder: ["radius_um", "height_um"],
  frustum: ["base_radius_um", "top_radius_um", "height_um"],
};

const DIM_LABEL: Record<string, string> = {
  radius_um: "Radius",
  height_um: "Height",
  base_radius_um: "Base radius",
  top_radius_um: "Top radius",
};

export const BODY_LABEL: Record<BodyControls["kind"], string> = {
  none: "Flat",
  hemisphere: "Dome",
  cylinder: "Pillar",
  frustum: "Taper",
  cad: "CAD",
};

// the numeric scene knobs the sliders drive (not the body / overlap-policy controls)
type NumericKey = "electrode_um" | "pitch_um" | "phase_width_us" | "neighbor_um" | "sigma_S_per_m";

interface Slider {
  key: NumericKey;
  label: string;
  min: number;
  max: number;
  step: number;
  unit: string;
  bipolarOnly?: boolean;
  decimals?: number;
}

// Ranges match the Dash app's, which are the ones the engine was exercised over.
// A narrower slider would silently put real configurations out of reach.
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
  uploadCad,
}: {
  controls: Controls;
  onChange: (next: Controls) => void;
  // uploads a CAD solid and returns its id; injected so the rail stays API-agnostic
  uploadCad?: (file: File) => Promise<{ upload_id: string; filename: string }>;
}) {
  const [cadName, setCadName] = useState<string | null>(null);
  const [cadError, setCadError] = useState<string | null>(null);
  const set = (patch: Partial<Controls>) => onChange({ ...controls, ...patch });
  // update a single field of the current body (dims / conductive_faces). Cast because
  // TS can't verify a dynamic-key spread stays within the discriminated union.
  const setBodyField = (patch: Record<string, unknown>) =>
    set({ body: { ...controls.body, ...patch } as BodyControls });
  const body = controls.body;
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
              {s.decimals ? controls[s.key].toFixed(s.decimals) : controls[s.key]} {s.unit}
            </b>
          </label>
          <input
            id={`c-${s.key}`}
            type="range"
            min={s.min}
            max={s.max}
            step={s.step}
            value={controls[s.key]}
            onChange={(e) => set({ [s.key]: Number(e.target.value) })}
          />
        </div>
      ))}

      {/* 3D electrode body: shapes the driven electrode e0. Anything but a flat disk
          is FEM-only (the analytical preview can't represent geometry), so Compare
          swaps the live field for a Run-FEM prompt when a body is set. */}
      <div className="ctl">
        <label>
          Electrode body<b>{body.kind === "none" ? "flat disk" : BODY_LABEL[body.kind]}</b>
        </label>
        <div className="seg" role="tablist" aria-label="Electrode body">
          {(["none", "hemisphere", "cylinder", "frustum", "cad"] as const).map((k) => (
            <button
              key={k}
              role="tab"
              aria-selected={body.kind === k}
              className={body.kind === k ? "on" : ""}
              onClick={() => {
                setCadError(null);
                if (k !== "cad") setCadName(null);
                set({ body: BODY_DEFAULTS[k] });
              }}
            >
              {BODY_LABEL[k]}
            </button>
          ))}
        </div>
      </div>

      {body.kind === "cad" && (
        <div className="ctl">
          <label htmlFor="body-cad">
            CAD solid<b>{body.upload_id ? (cadName ?? "loaded") : "STEP / BREP"}</b>
          </label>
          <input
            id="body-cad"
            type="file"
            accept=".step,.stp,.brep"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file || !uploadCad) return;
              setCadError(null);
              try {
                const up = await uploadCad(file);
                setCadName(up.filename);
                setBodyField({ upload_id: up.upload_id });
              } catch (err) {
                setCadError(err instanceof Error ? err.message : "upload failed");
              }
            }}
          />
          {cadError && (
            <span className="empty" role="alert">
              {cadError}
            </span>
          )}
        </div>
      )}

      {body.kind !== "none" && body.kind !== "cad" &&
        BODY_DIMS[body.kind].map((dim) => (
          <div className="ctl" key={dim}>
            <label htmlFor={`body-${dim}`}>
              {DIM_LABEL[dim]}
              <b>{(body as unknown as Record<string, number>)[dim]} µm</b>
            </label>
            <input
              id={`body-${dim}`}
              type="number"
              min={0.5}
              step={0.5}
              value={(body as unknown as Record<string, number>)[dim]}
              onChange={(e) => setBodyField({ [dim]: Number(e.target.value) })}
            />
          </div>
        ))}

      {"conductive_faces" in body && (
        <div className="ctl">
          <label>
            Conductive faces<b>{body.conductive_faces}</b>
          </label>
          <div className="seg" role="tablist" aria-label="Conductive faces">
            {(["tip", "sides", "all"] as const).map((f) => (
              <button
                key={f}
                role="tab"
                aria-selected={body.conductive_faces === f}
                className={body.conductive_faces === f ? "on" : ""}
                onClick={() => setBodyField({ conductive_faces: f })}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      )}

      {body.kind !== "none" && (
        <div className="ctl">
          <label>
            Cell overlap<b>{controls.overlap_policy}</b>
          </label>
          <div className="seg" role="tablist" aria-label="Cell overlap policy">
            {(["reject", "displace"] as const).map((p) => (
              <button
                key={p}
                role="tab"
                aria-selected={controls.overlap_policy === p}
                className={controls.overlap_policy === p ? "on" : ""}
                onClick={() => set({ overlap_policy: p })}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
