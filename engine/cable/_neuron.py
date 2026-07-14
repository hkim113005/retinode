"""Lazy NEURON access and on-demand mechanism compilation.

Importing this module does NOT import NEURON, so ``import engine.cable`` stays
light — NEURON is pulled in only when ``load()`` is called. The Fohlmeister-Miller
mechanisms are compiled on demand with ``nrnivmodl`` and cached in a platform arch
directory beside the ``.mod`` files, so tests and scripts work without a manual
build step. See ``mechanisms/PROVENANCE.md`` for the model source and license.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

MECHANISMS_DIR = Path(__file__).resolve().parent / "mechanisms"

# nrnivmodl output library, across platforms / NEURON versions.
_LIB_NAMES = ("libnrnmech.dylib", "libnrnmech.so", ".libs/libnrnmech.so")
_loaded = False


def compiled_library() -> Path | None:
    """Path to the compiled mechanism library, or None if not yet built."""
    for arch in MECHANISMS_DIR.iterdir():
        if not arch.is_dir():
            continue
        for name in _LIB_NAMES:
            lib = arch / name
            if lib.exists():
                return lib
    return None


def ensure_mechanisms_compiled() -> None:
    """Compile the .mod files with nrnivmodl if they are not already built."""
    if compiled_library() is not None:
        return
    result = subprocess.run(
        ["nrnivmodl", "."],
        cwd=MECHANISMS_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0 or compiled_library() is None:
        raise RuntimeError(
            "nrnivmodl failed to compile NEURON mechanisms:\n"
            + result.stdout
            + "\n"
            + result.stderr
        )


def load() -> Any:
    """Compile (if needed), load the mechanisms once, and return NEURON's ``h``."""
    global _loaded
    ensure_mechanisms_compiled()
    import neuron

    if not _loaded:
        neuron.load_mechanisms(str(MECHANISMS_DIR))
        _loaded = True
    from neuron import h

    return h
