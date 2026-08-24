"""The committed OpenAPI snapshot must match the live API.

``app/web/openapi.json`` is the contract the React client generates its TypeScript
types from (P7 S2). This test fails the moment the API's schema drifts from the
snapshot, so the types can never silently fall out of sync. Regenerate the snapshot
(``python -m api.export_schema`` / the export used in the build) when it does.
"""

import json
import pathlib

from api import create_app

_SNAPSHOT = pathlib.Path(__file__).resolve().parents[2] / "app" / "web" / "openapi.json"


def test_committed_openapi_snapshot_is_current():
    live = create_app().openapi()
    committed = json.loads(_SNAPSHOT.read_text())
    assert committed == live, (
        "app/web/openapi.json is stale: regenerate it (the API schema changed). "
        "The React client's generated TS types depend on this snapshot."
    )
