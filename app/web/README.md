# Retinode web client

The React + TypeScript client over the FastAPI engine, in the instrument-panel
visual language (see [`docs/phase-7-design.md`](../../docs/phase-7-design.md)).

Four screens, all reachable from the left rail and from the `⌘K` / `Ctrl-K`
command palette:

| screen | what it answers |
|---|---|
| **Compare** | what does the field around *this* geometry look like, and how wide is its selective operating window? Live analytical preview, isopotential contours, on-demand FEM solve, scorecard, run history, 3D loupe. |
| **Study** | which geometry in a diameter × pitch sweep wins? Runs the sweep as a job and plots the selectivity-versus-cost Pareto frontier. |
| **Candidates** | which charge-safe designs are worth testing in tissue? A ranked shortlist of the study's points, exportable as JSON or CSV. |
| **Validation** | should you believe any of it? Renders the committed reproduction report CI regenerates. |

Every plot exports as figure-quality SVG or high-DPI PNG.

## Prerequisites

- **Node 18 or newer** (Vite 5 and Vitest 2 both require it).
- **The API**, for anything that shows real numbers. The client talks to the
  FastAPI service on `:8000`; without it the screens load but every fetch fails
  with "Is the API running on :8000?". Type-checking and the test suite need no
  API, because the tests run against mocked responses.

## Run it

Two processes. Start the API first, from the repo root, in the `uv` env:

```bash
# 1) the API (from the repo root)
uv sync --extra cable --extra api
uv run uvicorn "api.main:create_app" --factory --port 8000
```

Then the client, from this folder (`app/web`):

```bash
# 2) the client; Vite proxies /api → :8000, so the browser sees one origin
npm install
npm run dev            # http://localhost:5173
```

The FEM tier ("Run accurately") and the Study sweep are served by the API out of
the separate conda `retinode-fem` env, not by anything in this folder. If those
buttons report a missing backend, the API is running without that env; see the
repo-root [`README.md`](../../README.md).

## Scripts

| script | what |
|---|---|
| `npm run dev` | Vite dev server on :5173 (proxies `/api` to the API on :8000) |
| `npm run build` | type-check + production build to `dist/` |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run test` | Vitest component tests (against mocked API responses) |
| `npm run gen:types` | regenerate `src/api/schema.d.ts` from `openapi.json` |

To run a single test file, or to watch: `npx vitest run src/screens/Study.test.tsx`,
`npx vitest` (watch mode).

## Layout

```
src/
  api/         typed client + schema types generated from openapi.json
  chart/       pure Scene builders and the canvas/SVG renderers (see chart/scene.ts)
  components/  panels and controls shared across screens
  screens/     Compare, Study, Candidates, Validation
  ui/          design tokens and global stylesheet
  test/        Vitest setup (RTL cleanup, WebGL stubs)
```

`chart/` holds the plots as pure data-to-`Scene` functions, deliberately outside
the components. Two renderers consume a `Scene`: canvas for the screen and SVG
for export. Because both eat the same description, an exported figure is what was
on screen and cannot drift into a second implementation.

## The contract

`openapi.json` is the committed OpenAPI snapshot of the API; `src/api/schema.d.ts`
is generated from it and `src/api/client.ts` is typed against it. Two guards keep
everything honest: a Python test (`tests/api/test_schema_snapshot.py`) fails if the
snapshot drifts from the live API, and CI fails if the generated types drift from the
snapshot.

After changing the API contract, regenerate both, from the repo root and then here:

```bash
uv run python -m api.export_schema   # rewrites app/web/openapi.json
cd app/web && npm run gen:types      # rewrites src/api/schema.d.ts
```

Never hand-edit `openapi.json` or `src/api/schema.d.ts`.
