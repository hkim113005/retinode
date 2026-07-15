"""Run the dashboard: ``python -m app`` (needs the ``app`` and ``cable`` extras)."""

from __future__ import annotations

from .ui import create_app

if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8050, debug=False)
