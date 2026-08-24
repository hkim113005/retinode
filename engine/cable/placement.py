"""Place an RGC in the patch: position at its soma + orient the axon (S6a).

The morphology is built at the template origin; `origin_um` carries it to the
cell's `soma_um` (added by segment_coords, so the field sees patch coordinates
with no pt3d surgery), and `axon_direction` points the appended axon toward the
optic disc (or along the spec's `axon_um`), so axons of passage cross the array
realistically.
"""

from __future__ import annotations

from engine.spec import RGC, RetinalPatch

from .channels import ChannelConfig, ChannelDensities, build_active_rgc
from .morphology import RGCModel

Vec3 = tuple[float, float, float]


def axon_direction(rgc: RGC, optic_disc: Vec3 | None) -> Vec3:
    """Direction the axon should run: along the spec's axon path if given, else
    toward the optic disc, else +x."""
    if rgc.axon_um and len(rgc.axon_um) >= 2:
        (x0, y0, z0), (x1, y1, z1) = rgc.axon_um[0], rgc.axon_um[-1]
        d: Vec3 = (x1 - x0, y1 - y0, z1 - z0)
    elif optic_disc is not None:
        sx, sy, sz = rgc.soma_um
        d = (optic_disc[0] - sx, optic_disc[1] - sy, optic_disc[2] - sz)
    else:
        d = (1.0, 0.0, 0.0)
    return d if d != (0.0, 0.0, 0.0) else (1.0, 0.0, 0.0)


def place_cell(
    rgc: RGC,
    *,
    optic_disc: Vec3 | None = None,
    densities: ChannelDensities | None = None,
    channel_config: ChannelConfig | None = None,
) -> RGCModel:
    """Build a ready-to-simulate RGC positioned at rgc.soma_um in the patch."""
    return build_active_rgc(
        rgc.cell_type,
        densities=densities,
        config=channel_config,
        origin_um=rgc.soma_um,
        axon_direction=axon_direction(rgc, optic_disc),
    )


def place_target(patch: RetinalPatch, **kwargs) -> RGCModel:
    """Place the patch's designated target cell."""
    return place_cell(patch.target(), optic_disc=patch.optic_disc_um, **kwargs)
