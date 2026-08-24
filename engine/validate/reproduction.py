"""A single literature reproduction: what we compared, and whether it holds.

Each check records its measured value, the criterion for passing, and the source:
the plan's "store target + tolerance + current value". The records both drive the
regression tests and feed the Validation dashboard later.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reproduction:
    name: str
    source: str
    passed: bool
    measured: str  # human-readable measured value(s), with units
    criterion: str  # what "passing" means
    note: str = ""  # caveats / interpretation (e.g. divergence from a claim)
