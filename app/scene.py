"""UI state → spec objects. Pure translation, no Dash, no engine computation.

A "scene" is the four spec objects an evaluation needs — array, stimulus,
patch, tissue — built from the handful of dashboard controls. Keeping this pure
means the whole input surface is testable without a browser or NEURON.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine import spec

# The array plane is z=0 and +z runs INTO the tissue, so cells sit at z>0 (D8; see
# docs/phase-6-plan.md and engine/spec/geometry.py). This used to be -20.0, which the
# analytical tier tolerated — its field is exactly mirror-symmetric about z=0, so the
# sign changed no number anywhere. It was still a landmine: every Phase-6 3D predicate
# assumes the +z convention (`point_in_body` tests `0 <= dz <= height_um`), so the
# moment an electrode carried a body, the overlap check would have silently matched
# nothing rather than failing loudly. `api/fem_job` was already papering over the sign
# with abs(). Fixed at the source instead.
_DEPTH_UM = 20.0
_OPTIC_DISC_UM = (2000.0, 0.0, _DEPTH_UM)


@dataclass(frozen=True)
class Scene:
    array: spec.ElectrodeArray
    config: spec.StimConfig
    patch: spec.RetinalPatch
    conductivity: spec.HomogeneousConductivity


def build_array(layout: str, electrode_um: float, pitch_um: float) -> spec.ElectrodeArray:
    """A single disk on the axis, or a bipolar pair split by ``pitch_um``."""
    if layout == "bipolar":
        half = pitch_um / 2.0
        return spec.ElectrodeArray(
            electrodes=(
                spec.Electrode(
                    id="e0", pos_um=(-half, 0.0, 0.0), shape="disk", size_um=electrode_um
                ),
                spec.Electrode(
                    id="e1", pos_um=(half, 0.0, 0.0), shape="disk", size_um=electrode_um
                ),
            )
        )
    return spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="e0", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=electrode_um),
        )
    )


def build_config(layout: str, phase_width_us: float) -> spec.StimConfig:
    """Cathodic drive. Single → monopolar (distant return); bipolar → local return."""
    waveform = spec.Waveform(phase_width_us=phase_width_us)
    if layout == "bipolar":
        return spec.StimConfig.from_map(
            {"e0": -1.0, "e1": 1.0}, waveform=waveform, distant_return=False
        )
    return spec.StimConfig.from_map({"e0": -1.0}, waveform=waveform, distant_return=True)


def build_patch(neighbor_um: float) -> spec.RetinalPatch:
    """A target cell under the array + one off-target neighbour at ``neighbor_um``."""
    return spec.RetinalPatch(
        cells=(
            spec.RGC(id="target", cell_type="parasol_on", soma_um=(0.0, 0.0, _DEPTH_UM)),
            spec.RGC(id="neighbor", cell_type="parasol_on", soma_um=(neighbor_um, 0.0, _DEPTH_UM)),
        ),
        target_id="target",
        optic_disc_um=_OPTIC_DISC_UM,
    )


def build_scene(
    *,
    layout: str,
    electrode_um: float,
    pitch_um: float,
    phase_width_us: float,
    neighbor_um: float,
    sigma_S_per_m: float,
) -> Scene:
    """Assemble the full scene from the dashboard controls."""
    return Scene(
        array=build_array(layout, electrode_um, pitch_um),
        config=build_config(layout, phase_width_us),
        patch=build_patch(neighbor_um),
        conductivity=spec.HomogeneousConductivity(sigma_S_per_m=sigma_S_per_m),
    )


def cell_depth_um() -> float:
    return _DEPTH_UM
