"""Lazy NEURON access and on-demand mechanism compilation.

Importing this module does NOT import NEURON, so ``import engine.cable`` stays
light — NEURON is pulled in only when ``load()`` is called. The Fohlmeister-Miller
mechanisms are compiled on demand with ``nrnivmodl`` and cached in a platform arch
directory beside the ``.mod`` files, so tests and scripts work without a manual
build step. See ``mechanisms/PROVENANCE.md`` for the model source and license.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

MECHANISMS_DIR = Path(__file__).resolve().parent / "mechanisms"

# The macOS NEURON.pkg installer prepends this to PYTHONPATH, which shadows the
# pip/conda NEURON in the active environment — often a build for a different
# Python, giving a cryptic "No module named 'neuron.hoc'".
_SHADOW_PATH_MARKER = "/Applications/NEURON"


def _import_neuron() -> Any:
    """Import NEURON, recovering if a broken installer copy shadows the real one."""
    try:
        import neuron

        return neuron
    except ImportError:
        shadows = [p for p in sys.path if _SHADOW_PATH_MARKER in p]
        if not shadows:
            raise  # a genuine NEURON problem, not the installer-shadow one
        # Drop the shadowing path + any half-initialized neuron modules, then retry
        # so the environment's own NEURON wheel is used instead.
        sys.path[:] = [p for p in sys.path if p not in shadows]
        for mod in [m for m in sys.modules if m == "neuron" or m.startswith("neuron.")]:
            del sys.modules[mod]
        import neuron

        return neuron

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
    neuron = _import_neuron()

    if not _loaded:
        neuron.load_mechanisms(str(MECHANISMS_DIR))
        _loaded = True
    from neuron import h

    return h
