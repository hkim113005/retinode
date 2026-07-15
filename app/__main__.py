"""Run the dashboard: ``python -m app`` (needs the ``app`` and ``cable`` extras).

``threaded=True`` matters: an evaluation runs NEURON for ~15-25 s, and without
threading the single-worker dev server stops servicing the request while it
blocks, so the result never returns and the button appears to do nothing. With
threading the server keeps responding and the callback completes normally.

``HOST``/``PORT`` are read from the environment (defaults 127.0.0.1:8050), which
also makes the app drop-in for a container/platform later.
"""

from __future__ import annotations

import os

from .ui import create_app

if __name__ == "__main__":
    create_app().run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8050")),
        debug=False,
        threaded=True,
    )
