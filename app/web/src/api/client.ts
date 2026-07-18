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
export type JobStatus = components["schemas"]["JobStatus"];
export type StudyControls = components["schemas"]["StudyControls"];
export type StudyPoint = components["schemas"]["StudyPoint"];
export type StudyResult = components["schemas"]["StudyResult"];
export type SweepControls = components["schemas"]["SweepControls"];
export type AmplitudeSweep = components["schemas"]["AmplitudeSweepResponse"];
export type ActivationCurve = components["schemas"]["ActivationCurve"];
export type ValidationReport = components["schemas"]["ValidationReport"];
export type ValidationReproduction = components["schemas"]["ValidationReproduction"];

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

// The scorecard runs as a background job (it needs a NEURON threshold search).
// Submit returns the job (already `done` when served from cache), then poll.
export async function postScore(controls: SceneControls): Promise<JobStatus> {
  const res = await fetch(`${BASE}/score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(controls),
  });
  if (!res.ok) throw new Error(`score failed (${res.status})`);
  return (await res.json()) as JobStatus;
}

// Upload a CAD solid (STEP/BREP). Returns the id a cad BodySpec references; the gmsh
// load happens later in the FEM job, so a bad solid surfaces then, not here.
export type CadUpload = components["schemas"]["CadUploadResponse"];
export async function postCad(file: File): Promise<CadUpload> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/cad`, { method: "POST", body: form });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `upload failed (${res.status})`);
  }
  return (await res.json()) as CadUpload;
}

export async function getJob(id: string): Promise<JobStatus> {
  const res = await fetch(`${BASE}/jobs/${id}`);
  if (!res.ok) throw new Error(`job poll failed (${res.status})`);
  return (await res.json()) as JobStatus;
}

// The trust panel: the committed reproductions report (served, never recomputed).
export async function getValidation(): Promise<ValidationReport> {
  const res = await fetch(`${BASE}/validation`);
  if (!res.ok) throw new Error(`validation failed (${res.status})`);
  return (await res.json()) as ValidationReport;
}

// Submit a geometry sweep (a job): returns points + Pareto frontier when done.
export async function postStudy(controls: StudyControls): Promise<JobStatus> {
  const res = await fetch(`${BASE}/study`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(controls),
  });
  if (!res.ok) throw new Error(`study failed (${res.status})`);
  return (await res.json()) as JobStatus;
}

// "Run accurately": solve the exact FEM field (dispatched to the conda env) as a
// job; the result carries the FEM field grid and its divergence from analytical.
export async function postAccurateField(controls: SceneControls): Promise<JobStatus> {
  const res = await fetch(`${BASE}/field/accurate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(controls),
  });
  if (!res.ok) throw new Error(`accurate field failed (${res.status})`);
  return (await res.json()) as JobStatus;
}

export async function postSweep(controls: SweepControls): Promise<JobStatus> {
  const res = await fetch(`${BASE}/sweep`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(controls),
  });
  if (!res.ok) throw new Error(`amplitude sweep failed (${res.status})`);
  return (await res.json()) as JobStatus;
}
