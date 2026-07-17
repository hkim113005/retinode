// The typed API client. Types come from src/api/schema.d.ts, generated from the
// FastAPI OpenAPI schema (`npm run gen:types`) — so the client can never drift from
// the server contract (docs/phase-7-plan.md, D2).
import type { components } from "./schema";

export type SceneControls = components["schemas"]["SceneControls"];
export type CompareResponse = components["schemas"]["CompareResponse"];
export type FieldGrid = components["schemas"]["FieldGridResponse"];
export type Scorecard = components["schemas"]["ScorecardResponse"];
export type ElectrodeMarker = components["schemas"]["ElectrodeMarker"];
export type CellMarker = components["schemas"]["CellMarker"];

// Dev: Vite proxies /api → the FastAPI server on :8000 (see vite.config.ts).
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export async function postCompare(
  controls: SceneControls,
  signal?: AbortSignal,
): Promise<CompareResponse> {
  const res = await fetch(`${BASE}/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(controls),
    signal,
  });
  if (!res.ok) throw new Error(`compare failed (${res.status})`);
  return (await res.json()) as CompareResponse;
}
