"""The architectural boundary that makes the Phase-7 re-skin a re-skin, not a
rewrite (docs/phase-7-plan.md, D1): ``engine/`` must not import ``api`` or ``app``.

The engine is the source of truth; the API and the client depend on it, never the
reverse. This lint is cheap and catches the one dependency direction that, if it
slipped, would couple the science to the UI.
"""

import pathlib
import re

_IMPORT = re.compile(r"^\s*(?:from|import)\s+(api|app)(?:\.|\s|$)", re.M)


def test_engine_never_imports_api_or_app():
    engine_dir = pathlib.Path(__file__).resolve().parents[2] / "engine"
    offenders = []
    for py in engine_dir.rglob("*.py"):
        for m in _IMPORT.finditer(py.read_text(encoding="utf-8")):
            offenders.append(f"{py.relative_to(engine_dir.parent)}: {m.group(0).strip()}")
    assert not offenders, "engine must not import api/app:\n" + "\n".join(offenders)
