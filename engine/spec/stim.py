"""StimConfig — the current delivery. References electrode ids only, NO geometry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .conventions import SCHEMA_VERSION


@dataclass(frozen=True)
class Waveform:
    """A biphasic pulse. Amplitude is signed by convention: cathodic (the
    excitatory leading phase) is negative current — see conventions.py."""

    phase_width_us: float
    amplitude_scale_uA: float = 1.0   # multiplies the per-electrode weights
    interphase_gap_us: float = 0.0
    cathodic_first: bool = True
    kind: Literal["biphasic"] = "biphasic"


@dataclass(frozen=True)
class StimConfig:
    """Which electrodes source and return current, with what relative weights.

    ``weights`` are signed relative currents per electrode id: sources > 0,
    returns < 0. The actual current is ``weight * waveform.amplitude_scale_uA``.

    ``distant_return`` distinguishes the two return regimes:
      * False (default) — a fully on-array config (e.g. Fan 2019 local return);
        the weights must charge-balance (sum ~ 0), checked in validation.
      * True — monopolar: the balancing current returns through a far ground
        that is not an array electrode, so on-array weights need not sum to 0.
    """

    weights: tuple[tuple[str, float], ...]   # (electrode_id, signed relative current)
    waveform: Waveform
    distant_return: bool = False
    schema_version: int = SCHEMA_VERSION

    def weight_map(self) -> dict[str, float]:
        return {eid: w for eid, w in self.weights}

    @classmethod
    def from_map(
        cls,
        weights: dict[str, float],
        waveform: Waveform,
        *,
        distant_return: bool = False,
    ) -> StimConfig:
        """Build from a dict; stored sorted by id so serialization is canonical."""
        return cls(
            weights=tuple(sorted(weights.items())),
            waveform=waveform,
            distant_return=distant_return,
        )
