"""P5 S2: geometry sweep -> Pareto frontier (injected provider, no NEURON/FEM).

One end-to-end test (neuron-marked) runs a real geometry sweep on the analytical
tier to confirm the outer loop drives real fields + threshold searches, not just a
stub."""

from __future__ import annotations

import pytest

from engine import spec
from engine.cable.population import PopulationThresholds
from engine.field import AnalyticalBackend, FenicsxBackend
from engine.spec.conductivity import Layer
from engine.store.project import Project
from engine.study.geometry import ArrayGeometry, build_array
from engine.study.geometry_sweep import (
    geometry_sweep,
    monopolar_center,
    resolve_field_tier,
)

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
PATCH = spec.RetinalPatch(
    cells=(
        spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),
        spec.RGC(id="n1", cell_type="parasol_on", soma_um=(40.0, 0.0, -20.0)),
    ),
    target_id="t",
    optic_disc_um=(2000.0, 0.0, -20.0),
)
GEOMS = [
    ArrayGeometry(10.0, 30.0, "grid", 30.0),  # 5 electrodes
    ArrayGeometry(10.0, 30.0, "grid", 60.0),  # denser
    ArrayGeometry(10.0, 30.0, "hex", 60.0),  # different lattice/count
]


def _provider():
    # denser arrays: slightly higher target (less safe) but much higher off-target
    # threshold (more selective) -> a genuine selectivity/safety trade-off.
    def provider(patch, array, config, conductivity, *, off_target_set=None, backend=None, **_):
        n = len(array.electrodes)
        return PopulationThresholds(patch.target_id, 6.0 + 0.5 * n, {"n1": 6.0 + 3.0 * n})

    return provider


def test_geometry_sweep_covers_every_geometry_and_builds_a_frontier():
    res = geometry_sweep(GEOMS, PATCH, COND, monopolar_center, thresholds_provider=_provider())

    assert res.n_geometries == 3
    assert all(len(o.results) == 1 for o in res.outcomes)  # one config each
    assert all(o.backend_name == "analytical" for o in res.outcomes)  # homogeneous -> analytical

    # the frontier is a non-empty subset of all results, tracing back to geometries
    assert len(res.pareto) >= 1
    all_keys = {r.result_key for r in res.all_results}
    assert all(r.result_key in all_keys for r in res.pareto)
    for r in res.pareto:
        assert res.geometry_of(r) in GEOMS
    assert set(res.pareto_geometries) <= set(GEOMS)


def test_frontier_is_non_dominated():
    res = geometry_sweep(GEOMS, PATCH, COND, monopolar_center, thresholds_provider=_provider())

    # re-derive selectivity/safety objectives; no frontier point is dominated
    def obj(r):
        return (r.sow.ratio, r.window.safety_ceiling_uA / r.window.target_uA)

    front = [obj(r) for r in res.pareto]
    for a in front:
        assert not any(
            b != a and b[0] >= a[0] and b[1] >= a[1] and (b[0] > a[0] or b[1] > a[1]) for b in front
        )


def test_store_makes_a_re_run_fully_cached(tmp_path):
    store = Project.open(tmp_path / "geo")
    first = geometry_sweep(
        GEOMS, PATCH, COND, monopolar_center, store=store, thresholds_provider=_provider()
    )
    assert first.n_cached == 0
    second = geometry_sweep(
        GEOMS, PATCH, COND, monopolar_center, store=store, thresholds_provider=_provider()
    )
    assert second.n_cached == len(second.all_results)  # every result served from disk


def test_on_geometry_progress_callback_fires_per_geometry():
    seen: list[int] = []
    geometry_sweep(
        GEOMS,
        PATCH,
        COND,
        monopolar_center,
        thresholds_provider=_provider(),
        on_geometry=lambda i, outcome: seen.append(i),
    )
    assert seen == [0, 1, 2]


def test_explicit_backend_overrides_tier_selection():
    res = geometry_sweep(
        GEOMS[:1],
        PATCH,
        COND,
        monopolar_center,
        backend=AnalyticalBackend(),
        thresholds_provider=_provider(),
    )
    assert res.outcomes[0].backend_name == "analytical"


# --- regime-aware tier selection (D2) ---------------------------------------


def test_resolve_field_tier_homogeneous_uses_analytical():
    backend, cond = resolve_field_tier(COND)
    assert backend.name == "analytical"
    assert cond is COND


def test_resolve_field_tier_mild_layers_approximate_as_homogeneous():
    mild = spec.LayeredConductivity(layers=(Layer(1.0, 40.0), Layer(1.05, 60.0)))
    backend, cond = resolve_field_tier(mild, contrast_tol=0.1)
    assert backend.name == "analytical"  # 5% contrast is within the trustworthy regime
    assert isinstance(cond, spec.HomogeneousConductivity)
    assert cond.sigma_S_per_m == 1.0  # the surface layer's sigma


def test_resolve_field_tier_strong_contrast_escalates_to_fem():
    strong = spec.LayeredConductivity(layers=(Layer(1.0, 40.0), Layer(0.3, 60.0)))
    backend, cond = resolve_field_tier(strong)
    assert isinstance(backend, FenicsxBackend)
    assert cond is strong  # the true layered conductivity is solved, not approximated


# --- the default config factory ---------------------------------------------


def test_monopolar_center_drives_the_central_electrode():
    array = build_array(ArrayGeometry(10.0, 30.0, "grid", 60.0))
    (config,) = monopolar_center(array)
    weights = config.weight_map()
    assert len(weights) == 1
    (driven_id,) = weights
    driven = array.by_id(driven_id)
    assert driven.pos_um[:2] == (0.0, 0.0)  # the centre electrode
    assert weights[driven_id] == -1.0  # cathodic


# --- end-to-end on real fields + NEURON (the composition, not a stub) --------

_E2E_PATCH = spec.RetinalPatch(
    cells=(
        spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),
        spec.RGC(id="n1", cell_type="parasol_on", soma_um=(40.0, 0.0, -20.0)),
        spec.RGC(id="far", cell_type="parasol_on", soma_um=(500.0, 0.0, -20.0)),
    ),
    target_id="t",
    optic_disc_um=(2000.0, 0.0, -20.0),
)
# two single-electrode geometries differing only in electrode diameter -> genuinely
# different near-field and safety ceiling under the monopolar-centre protocol.
_E2E_GEOMS = [
    ArrayGeometry(8.0, 40.0, "grid", 0.0),
    ArrayGeometry(16.0, 40.0, "grid", 0.0),
]


@pytest.mark.neuron
@pytest.mark.slow
def test_real_geometry_sweep_runs_and_resumes(neuron_h, tmp_path):
    store = Project.open(tmp_path / "geo")
    res = geometry_sweep(_E2E_GEOMS, _E2E_PATCH, COND, monopolar_center, store=store)

    assert res.n_geometries == 2
    assert all(len(o.results) == 1 for o in res.outcomes)
    assert all(r.activated for r in res.all_results)  # real threshold searches fired
    assert all(o.backend_name == "analytical" for o in res.outcomes)
    for r in res.pareto:  # frontier points trace back to the real geometries
        assert res.geometry_of(r) in _E2E_GEOMS

    # a resumed run recomputes nothing (the "without manual bookkeeping" clause)
    again = geometry_sweep(_E2E_GEOMS, _E2E_PATCH, COND, monopolar_center, store=store)
    assert again.n_cached == len(again.all_results)


def test_geometry_field_tier_is_always_fem():
    """Comparing geometry means FEM, whatever the conductivity: only a field solve
    that resolves the electrode surface can tell one diameter from another."""
    from engine.field import FenicsxBackend
    from engine.study.geometry_sweep import geometry_field_tier

    backend, cond = geometry_field_tier(COND)
    assert isinstance(backend, FenicsxBackend)
    assert cond is COND  # geometry, not conductivity, forced the choice


def test_geometry_varies_keys_on_diameter():
    from engine.study.geometry import ArrayGeometry
    from engine.study.geometry_sweep import geometry_varies

    def g(d, p):
        return ArrayGeometry(diameter_um=d, pitch_um=p, arrangement="hex", aperture_um=60.0)

    assert geometry_varies([g(8, 40), g(20, 40)]) is True  # different diameter
    assert geometry_varies([g(10, 30), g(10, 70)]) is False  # only pitch moves
    assert geometry_varies([g(10, 40)]) is False  # a single geometry compares nothing


def test_a_diameter_sweep_on_the_analytical_tier_is_a_loud_error():
    """The silent-flat-frontier bug, now a raised error at the engine boundary."""
    from engine.field import AnalyticalBackend
    from engine.study.geometry import ArrayGeometry
    from engine.study.geometry_sweep import (
        GeometryTierError,
        require_geometry_distinguishable,
    )

    def g(d):
        return ArrayGeometry(diameter_um=d, pitch_um=40.0, arrangement="hex", aperture_um=60.0)

    with pytest.raises(GeometryTierError, match="point source"):
        require_geometry_distinguishable([g(8), g(24)], AnalyticalBackend())

    # a single geometry, or a pitch-only sweep, has nothing the analytical tier
    # provably cannot see — no error
    require_geometry_distinguishable([g(10)], AnalyticalBackend())


def test_the_fem_tier_is_never_guarded_out():
    """FEM sees geometry, so a diameter sweep on it is exactly right — no error."""
    from engine.field import FenicsxBackend
    from engine.study.geometry import ArrayGeometry
    from engine.study.geometry_sweep import require_geometry_distinguishable

    def g(d):
        return ArrayGeometry(diameter_um=d, pitch_um=40.0, arrangement="hex", aperture_um=60.0)

    require_geometry_distinguishable([g(8), g(24)], FenicsxBackend())  # no raise
