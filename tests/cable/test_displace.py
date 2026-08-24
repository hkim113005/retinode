"""P6 S4 wired end-to-end: the ``displace`` overlap policy actually drives NEURON.

A penetrating electrode body is planted so it swallows the target's soma and some
proximal compartments. Then:

- ``reject`` refuses the scene (raises), and
- ``displace`` severs the interior compartments. It never queries the field there
  (the point is inside the metal, which the FEM backend would reject) and never
  detects a spike there, yet the cell still reaches threshold on its surviving,
  outside-the-metal compartments.

Uses the analytical backend (a point/disk source, fast, no FEM env). The property
that severed compartments are excluded from the field *query* is backend-agnostic,
so proving it here also protects the FEM path, where querying an interior point
raises.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine import spec
from engine.cable.drive import segment_coords
from engine.cable.placement import place_cell
from engine.cable.population import population_thresholds, severed_segments
from engine.eval.overlap import OverlapConflict
from engine.field import AnalyticalBackend

pytestmark = pytest.mark.neuron

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)


class _PointRecordingBackend:
    """Analytical backend that records every query-point array it is asked to solve."""

    name = "analytical"

    def __init__(self) -> None:
        self._inner = AnalyticalBackend()
        self.queried: list[np.ndarray] = []

    def transfer_matrix(self, array, conductivity, query_points_um):
        pts = np.asarray(query_points_um, dtype=float)
        self.queried.append(pts)
        return self._inner.transfer_matrix(array, conductivity, pts)


def _penetrating_scene():
    # Target soma at +z inside the tissue; a cylinder body at the origin, tall and
    # wide enough to swallow the soma and its proximal compartments. A distant
    # off-target keeps the population non-trivial and clear of the metal.
    patch = spec.RetinalPatch(
        cells=(
            spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, 12.0)),
            spec.RGC(id="n1", cell_type="parasol_on", soma_um=(60.0, 0.0, 12.0)),
        ),
        target_id="t",
        optic_disc_um=(2000.0, 0.0, 12.0),
    )
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(
                id="e", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=0.0,
                body=spec.Cylinder(radius_um=14.0, height_um=30.0, conductive_faces="all"),
            ),
        )
    )
    config = spec.StimConfig.from_map(
        {"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0), distant_return=True
    )
    return patch, array, config


def test_the_body_actually_swallows_some_target_compartments(neuron_h):
    patch, array, _ = _penetrating_scene()
    model = place_cell(patch.cells[0], optic_disc=patch.optic_disc_um)
    severed = severed_segments(model, array)
    assert severed, "test geometry must put some compartments inside the body"
    # every severed index is genuinely inside the cylinder (radius 14, height 30)
    coords, _ = segment_coords(model)
    for i in severed:
        x, y, z = coords[i]
        assert np.hypot(x, y) <= 14.0 + 1e-9 and 0.0 <= z <= 30.0 + 1e-9


def test_reject_policy_refuses_the_penetrating_scene(neuron_h):
    patch, array, config = _penetrating_scene()
    with pytest.raises(OverlapConflict, match=r"cell 't'.*inside an electrode body"):
        population_thresholds(patch, array, config, COND, overlap_policy="reject")


def test_displace_severs_the_interior_and_survivors_still_fire(neuron_h):
    patch, array, config = _penetrating_scene()
    model = place_cell(patch.cells[0], optic_disc=patch.optic_disc_um)
    severed = severed_segments(model, array)
    coords, _ = segment_coords(model)
    spy = _PointRecordingBackend()

    r = population_thresholds(
        patch, array, config, COND, backend=spy, overlap_policy="displace"
    )

    # the target still activates, on its surviving compartments
    assert r.target_threshold_uA is not None and r.target_threshold_uA > 0.0

    # and the field was never queried at a severed (in-metal) compartment: the
    # property the FEM backend relies on, since an interior point there raises
    severed_xyz = {tuple(np.round(coords[i], 6)) for i in severed}
    for pts in spy.queried:
        queried_xyz = {tuple(np.round(p, 6)) for p in pts}
        assert severed_xyz.isdisjoint(queried_xyz)
