# Retinode web client (Phase 7)

The React + TypeScript client over the FastAPI engine, in the instrument-panel
visual language (see `docs/phase-7-design.md`). S2 ships the **Compare** screen: a
live analytical field preview with an on-demand operating-window scorecard.

## Run it

```bash
# 1) the API (from the repo root, uv env)
uv run uvicorn "api.main:create_app" --factory --port 8000

# 2) the client (this folder) — Vite proxies /api → :8000
npm install
npm run dev            # http://localhost:5173
```

## Scripts

| script | what |
|---|---|
| `npm run dev` | Vite dev server (proxies `/api` to the API on :8000) |
| `npm run build` | type-check + production build to `dist/` |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run test` | Vitest component tests (against mocked API responses) |
| `npm run gen:types` | regenerate `src/api/schema.d.ts` from `openapi.json` |

## The contract

`openapi.json` is the committed OpenAPI snapshot of the API; `src/api/schema.d.ts`
is generated from it and `src/api/client.ts` is typed against it. Two guards keep
everything honest: a Python test (`tests/api/test_schema_snapshot.py`) fails if the
snapshot drifts from the live API, and CI fails if the generated types drift from the
snapshot. After changing the API contract, run `python -m api.export_schema` then
`npm run gen:types`.
