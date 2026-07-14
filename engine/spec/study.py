"""StudyDefinition — a parameter sweep over the other specs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .conventions import SCHEMA_VERSION

# The accuracy tier a study runs at (attached to every result downstream).
Tier = Literal["analytical", "fem", "cross_checked"]


@dataclass(frozen=True)
class Sweep:
    """One varied parameter: a dotted path into a spec, and the values to try.

    e.g. path="stim.waveform.phase_width_us", values=(50.0, 100.0, 200.0)
    or   path="array.electrodes.0.size_um" for a geometry sweep.
    """

    path: str
    values: tuple[float, ...]

    @classmethod
    def linspace(cls, path: str, start: float, stop: float, num: int) -> Sweep:
        if num < 2:
            values: tuple[float, ...] = (float(start),)
        else:
            step = (stop - start) / (num - 1)
            values = tuple(start + i * step for i in range(num))
        return cls(path=path, values=values)


@dataclass(frozen=True)
class StudyDefinition:
    """The parameters to vary, the tier to run at, and the objectives to record."""

    sweeps: tuple[Sweep, ...]
    tier: Tier = "analytical"
    objectives: tuple[str, ...] = ("sow",)   # e.g. selective operating window
    schema_version: int = SCHEMA_VERSION
