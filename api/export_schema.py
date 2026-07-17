"""Write the OpenAPI schema to ``app/web/openapi.json``.

The React client generates its TypeScript types from this snapshot, and a test
(``tests/api/test_schema_snapshot.py``) keeps it in lockstep with the live API. Run
``python -m api.export_schema`` after any change to the API contract.
"""

from __future__ import annotations

import json
import pathlib

from api import create_app

_SNAPSHOT = pathlib.Path(__file__).resolve().parents[1] / "app" / "web" / "openapi.json"


def main() -> None:
    schema = create_app().openapi()
    _SNAPSHOT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {_SNAPSHOT} — paths: {sorted(schema['paths'])}")


if __name__ == "__main__":
    main()
