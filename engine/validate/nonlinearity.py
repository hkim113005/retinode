"""Vilkhu 2025: multi-electrode currents summate (P3 S3).

Two nearby electrodes each depolarise the target's spike-initiation zone. At a
shared amplitude that is *subthreshold for either electrode alone*, the two
currents summate and jointly cross threshold — the paired threshold falls well
below either single-electrode threshold. A model that treated the electrodes as
independent (activation at the lower single-electrode threshold) would miss this;
the full multi-compartment model captures it. This is the multi-site activation
property (a spike anywhere counts) doing exactly what it was built for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine import spec

from .reproduction import Reproduction

if TYPE_CHECKING:
    from engine.cable.morphology import RGCModel

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
_WAVE = spec.Waveform(phase_width_us=200.0)
_SPACING_UM = 18.0  # two electrodes straddling the soma, close enough to summate


def _array(spacing_um: float = _SPACING_UM) -> spec.ElectrodeArray:
    return spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="A", pos_um=(-spacing_um, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(id="B", pos_um=(spacing_um, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )


def _threshold(cell: RGCModel, weights: dict[str, float], spacing_um: float) -> float | None:
    from engine.cable.multisite import multisite_threshold

    config = spec.StimConfig.from_map(weights, waveform=_WAVE, distant_return=True)
    return multisite_threshold(
        cell, _array(spacing_um), config, COND, amp_min=2.0, amp_max=400.0
    ).threshold_uA


def subthreshold_electrodes_summate(
    cell: RGCModel, spacing_um: float = _SPACING_UM
) -> Reproduction:
    """Paired-electrode threshold vs each single-electrode threshold (NEURON).

    ``cell`` is an active RGC at the origin with its axon perpendicular to the
    electrode axis, so the two electrodes contribute symmetrically to the AIS.
    """
    t_a = _threshold(cell, {"A": -1.0}, spacing_um)
    t_b = _threshold(cell, {"B": -1.0}, spacing_um)
    t_ab = _threshold(cell, {"A": -1.0, "B": -1.0}, spacing_um)

    if t_a is None or t_b is None or t_ab is None:
        return Reproduction(
            name="two subthreshold electrodes jointly fire (current summation)",
            source="Vilkhu et al. 2025",
            passed=False,
            measured="a threshold was not found in range",
            criterion="paired-electrode threshold falls below either single-electrode threshold",
        )

    single = min(t_a, t_b)
    return Reproduction(
        name="two subthreshold electrodes jointly fire (current summation)",
        source="Vilkhu et al. 2025",
        passed=t_ab < single,
        measured=(
            f"threshold each: A {t_a:.0f}, B {t_b:.0f} µA alone; "
            f"paired {t_ab:.0f} µA ({t_ab / single:.0%} of single)"
        ),
        criterion="paired-electrode threshold falls below either single-electrode threshold",
    )
