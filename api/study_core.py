"""The geometry sweep, FastAPI- and Pydantic-free (P8 S4).

This is the orchestration behind ``POST /study``, factored out of the route so it can
run in TWO places from one implementation:

- **in the uv API process** with an injected fake ``thresholds_provider`` (dev, tests)
  — fast, NEURON-free, the field backend is cosmetic there;
- **in the conda ``retinode-fem`` env** via :mod:`api.study_job`, on the real FEM
  tier with real NEURON — because comparing electrode geometry is FEM-only (the
  analytical point source is diameter-blind; ``docs/phase-8-findings.md``).

It takes and returns **plain dicts**, no Pydantic, so it imports cleanly in the FEM
env (which has no FastAPI). The route wraps the result in ``StudyResult``.
"""

from __future__ import annotations

from collections.abc import Callable

from app.scene import build_patch
from engine.field import AnalyticalBackend, FieldBackend
from engine.spec import HomogeneousConductivity
from engine.study.geometry import geometry_grid
from engine.study.geometry_sweep import (
    geometry_field_tier,
    geometry_sweep,
    monopolar_center,
    require_geometry_distinguishable,
)
from engine.study.spread import geometry_trajectory_spread
from engine.study.sweep import ThresholdsProvider

ProgressFn = Callable[[float, str], None]


def _query_reach_um(patch) -> float:  # noqa: ANN001 - a RetinalPatch
    """Farthest radial distance any cell compartment reaches from the array axis.

    This is what the FEM domain must contain: the field is sampled at every
    compartment, and the axon of passage runs far toward the optic disc.
    """
    import math

    from engine.cable.drive import segment_coords
    from engine.cable.placement import place_cell

    reach = 0.0
    for rgc in patch.cells:
        coords, _ = segment_coords(place_cell(rgc, optic_disc=patch.optic_disc_um))
        reach = max(reach, *(math.hypot(p[0], p[1]) for p in coords))
    return reach


def _frontier_points(sweep, spreads) -> list[dict]:  # noqa: ANN001 - a GeometrySweepResult
    """Reduce a completed sweep to points, marking the selectivity-versus-cost
    frontier: a safe point is on it if no other safe point beats it on both axes.
    Master-plan §15, distinct from the engine's selectivity-vs-safety pareto.

    Plain dicts, so the conda job can emit JSON without Pydantic."""
    raw = [
        {
            "diameter_um": o.geometry.diameter_um,
            "pitch_um": o.geometry.pitch_um,
            "cost_uA": r.window.target_uA,
            "selectivity_uA": r.window.usable_margin_uA,
            "safe": bool(r.safety_at_target and r.safety_at_target.safe),
            "spread_uA": (spreads or {}).get((o.geometry.diameter_um, o.geometry.pitch_um)),
        }
        for o in sweep.outcomes
        for r in o.results
        if r.activated and r.window is not None
    ]

    def dominated(p: dict) -> bool:
        # the frontier is selectivity-vs-cost only; the spread is a reported error
        # bar, not a third axis to be dominated on
        return any(
            q is not p
            and q["safe"]
            and q["cost_uA"] <= p["cost_uA"]
            and q["selectivity_uA"] >= p["selectivity_uA"]
            and (q["cost_uA"] < p["cost_uA"] or q["selectivity_uA"] > p["selectivity_uA"])
            for q in raw
        )

    return [{**p, "on_frontier": p["safe"] and not dominated(p)} for p in raw]


def run_study(
    controls: dict,
    *,
    thresholds_provider: ThresholdsProvider | None = None,
    backend: FieldBackend | None = None,
    on_progress: ProgressFn | None = None,
) -> dict:
    """Run the diameter × pitch sweep and return ``{points, n_geometries}`` as plain
    dicts.

    Backend: an injected ``thresholds_provider`` short-circuits the field solve, so
    the backend is cosmetic and defaults to analytical (fast, for dev/tests). The real
    path (``thresholds_provider is None``) forces the **FEM** tier, because only a
    surface-resolving field distinguishes one diameter from another — and guards that
    a geometry-varying sweep never silently runs on the diameter-blind analytical tier.
    """
    report = on_progress or (lambda _f, _m: None)

    geometries = geometry_grid(
        diameters_um=controls["diameters_um"],
        pitches_um=controls["pitches_um"],
        arrangement=controls.get("arrangement", "hex"),
        aperture_um=controls.get("aperture_um", 120.0),
    )
    n = max(1, len(geometries))
    patch = build_patch(controls.get("neighbor_um", 40.0))
    conductivity = HomogeneousConductivity(sigma_S_per_m=controls.get("sigma_S_per_m", 1.0))

    if backend is None:
        if thresholds_provider is not None:
            backend = AnalyticalBackend()  # cosmetic under a fake provider
        else:
            # The FEM domain must contain every point the field is sampled at — the
            # cell compartments, whose axon of passage reaches hundreds of µm toward
            # the optic disc, far outside a domain sized for a small electrode. Floor
            # the domain at the query reach (+margin), or the solve raises on a point
            # outside the mesh (found the hard way running this live).
            reach = _query_reach_um(patch)
            backend = geometry_field_tier(conductivity, min_half_width_um=reach * 1.15)[0]
    # only the real field path can be fooled by a geometry-blind tier; a provider makes
    # the backend cosmetic, so the guard would be a false alarm there
    if thresholds_provider is None:
        require_geometry_distinguishable(geometries, backend)

    phase_width_us = controls.get("phase_width_us", 200.0)

    def config_factory(array):
        return monopolar_center(array, phase_width_us=phase_width_us)

    def on_geometry(index: int, _outcome) -> None:
        report((index + 1) / n * 0.85, f"solving geometry {index + 1} of {n}")

    report(0.02, f"sweeping {n} geometries")
    sweep = geometry_sweep(
        geometries,
        patch,
        conductivity,
        config_factory,
        backend=backend,
        thresholds_provider=thresholds_provider,
        on_geometry=on_geometry,
    )

    # opt-in trajectory spread (k=1 = off), after the sweep so a failed spread never
    # costs the frontier. On the FEM tier this is k× the FEM cost per geometry.
    spreads = None
    k = int(controls.get("trajectory_k", 1))
    if k > 1:
        report(0.9, f"sampling {k} axon trajectories per geometry")
        spreads = geometry_trajectory_spread(
            geometries,
            patch,
            config_factory,
            conductivity,
            k=k,
            jitter_deg=controls.get("trajectory_jitter_deg", 15.0),
            backend=backend,
        )

    return {
        "points": _frontier_points(sweep, spreads),
        "n_geometries": sweep.n_geometries,
        # Derived from the backend that actually ran, not from which branch the route
        # took, so an explicitly passed backend= is reported honestly too. Candidates
        # exports this; it used to hardcode "analytical" while production sweeps have
        # run on FEM since P8 S4b, so every exported shortlist claimed the wrong tier.
        "tier": "analytical" if isinstance(backend, AnalyticalBackend) else "fem",
    }
