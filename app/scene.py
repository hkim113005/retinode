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


def body_from_spec(d: dict | None) -> spec.ElectrodeBody | None:
    """Translate a contract body dict to an ``engine.spec`` primitive body.

    ``None`` / ``{"kind": "none"}`` -> a flat electrode (no body). The primitives
    (hemisphere / cylinder / frustum) resolve here, in the uv env, with no gmsh. A
    ``"cad"`` body cannot be built here — it needs gmsh to read the solid — so this
    raises; the FEM jobs resolve CAD via ``engine.field.mesh3d.load_cad_body`` in the
    conda env and pass the resulting ``CadBody`` straight to ``build_scene``.
    """
    if d is None or d.get("kind", "none") == "none":
        return None
    kind = d["kind"]
    if kind == "hemisphere":
        return spec.Hemisphere(radius_um=d["radius_um"])
    if kind == "cylinder":
        return spec.Cylinder(
            radius_um=d["radius_um"],
            height_um=d["height_um"],
            conductive_faces=d.get("conductive_faces", "all"),
        )
    if kind == "frustum":
        return spec.Frustum(
            base_radius_um=d["base_radius_um"],
            top_radius_um=d["top_radius_um"],
            height_um=d["height_um"],
            conductive_faces=d.get("conductive_faces", "all"),
        )
    if kind == "cad":
        raise ValueError("CAD bodies must be resolved with load_cad_body in the FEM env")
    raise ValueError(f"unknown electrode body kind: {kind!r}")


def build_array(
    layout: str,
    electrode_um: float,
    pitch_um: float,
    *,
    body: spec.ElectrodeBody | None = None,
) -> spec.ElectrodeArray:
    """A single disk on the axis, or a bipolar pair split by ``pitch_um``.

    ``body`` (if given) is attached to the *driven* electrode ``e0`` only; a bipolar
    return ``e1`` stays a flat disk (shaping the return is out of scope for now)."""
    if layout == "bipolar":
        half = pitch_um / 2.0
        return spec.ElectrodeArray(
            electrodes=(
                spec.Electrode(
                    id="e0", pos_um=(-half, 0.0, 0.0), shape="disk", size_um=electrode_um, body=body
                ),
                spec.Electrode(
                    id="e1", pos_um=(half, 0.0, 0.0), shape="disk", size_um=electrode_um
                ),
            )
        )
    return spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(
                id="e0", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=electrode_um, body=body
            ),
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
    body: spec.ElectrodeBody | None = None,
) -> Scene:
    """Assemble the full scene from the dashboard controls.

    ``body`` shapes the driven electrode ``e0`` (a 3D pillar/dome/taper/CAD solid);
    ``None`` is the flat disk the analytical tier handles. A bodied scene is FEM-only
    — the analytical field is a point source blind to the body — so the caller must
    solve it on ``FenicsxBackend`` (the API routes a bodied scene to the conda env)."""
    return Scene(
        array=build_array(layout, electrode_um, pitch_um, body=body),
        config=build_config(layout, phase_width_us),
        patch=build_patch(neighbor_um),
        conductivity=spec.HomogeneousConductivity(sigma_S_per_m=sigma_S_per_m),
    )


def cell_depth_um() -> float:
    return _DEPTH_UM
