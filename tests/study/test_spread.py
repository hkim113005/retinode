"""P8 S3: the trajectory spread lifted from one cell to a geometry sweep."""

import math

import pytest

from engine.study.geometry import ArrayGeometry
from engine.study.spread import geometry_trajectory_spread


def _geoms():
    return [
        ArrayGeometry(diameter_um=10.0, pitch_um=40.0, arrangement="hex", aperture_um=60.0),
        ArrayGeometry(diameter_um=20.0, pitch_um=60.0, arrangement="hex", aperture_um=60.0),
    ]


def test_each_geometry_is_configured_from_its_own_array(monkeypatch):
    """A config's weight map keys are THAT array's electrode ids, so a config built
    for one geometry is meaningless against another. Pins the factory contract."""
    seen: list[tuple[float, int]] = []

    def factory(array):
        from engine.spec import StimConfig, Waveform

        seen.append((array.electrodes[0].size_um, len(array.electrodes)))
        return [
            StimConfig.from_map(
                {array.electrodes[0].id: -1.0}, waveform=Waveform(phase_width_us=200.0)
            )
        ]

    def fake_spread(rgc, array, config, conductivity, **kw):
        from engine.cable.trajectories import TrajectorySpread

        # the config we were handed must name an electrode of THIS array
        ids = {e.id for e in array.electrodes}
        named = {eid for eid, _w in config.weights}
        assert named <= ids, "config built for a different array"
        return TrajectorySpread((10.0, 11.0), ((1.0, 0.0, 0.0),), 10.5, 0.5, 0.05)

    monkeypatch.setattr("engine.study.spread.trajectory_spread", fake_spread)
    from app.scene import build_patch

    out = geometry_trajectory_spread(_geoms(), build_patch(40.0), factory, None, k=3)
    assert len(seen) == 2  # the factory ran per geometry, not once
    assert seen[0][0] == 10.0 and seen[1][0] == 20.0
    assert out[(10.0, 40.0)] == 0.5


def test_a_single_sample_yields_no_spread(monkeypatch):
    """A std needs >= 2 samples. One is not an error bar, and must not render as 0."""
    from engine.spec import StimConfig, Waveform

    def factory(array):
        return [
            StimConfig.from_map(
                {array.electrodes[0].id: -1.0}, waveform=Waveform(phase_width_us=200.0)
            )
        ]

    def one_sample(rgc, array, config, conductivity, **kw):
        from engine.cable.trajectories import TrajectorySpread

        return TrajectorySpread((10.0,), ((1.0, 0.0, 0.0),), 10.0, None, None)

    monkeypatch.setattr("engine.study.spread.trajectory_spread", one_sample)
    from app.scene import build_patch

    out = geometry_trajectory_spread(_geoms(), build_patch(40.0), factory, None, k=1)
    assert out[(10.0, 40.0)] is None
    assert out[(20.0, 60.0)] is None


def test_a_silent_target_yields_no_spread(monkeypatch):
    """If the target never fired on any trajectory there is nothing to spread."""
    from engine.spec import StimConfig, Waveform

    def factory(array):
        return [
            StimConfig.from_map(
                {array.electrodes[0].id: -1.0}, waveform=Waveform(phase_width_us=200.0)
            )
        ]

    def silent(rgc, array, config, conductivity, **kw):
        from engine.cable.trajectories import TrajectorySpread

        return TrajectorySpread((), ((1.0, 0.0, 0.0),), None, None, None)

    monkeypatch.setattr("engine.study.spread.trajectory_spread", silent)
    from app.scene import build_patch

    out = geometry_trajectory_spread(_geoms(), build_patch(40.0), factory, None, k=3)
    assert all(v is None for v in out.values())


def test_an_empty_protocol_is_not_a_zero_spread(monkeypatch):
    from app.scene import build_patch

    out = geometry_trajectory_spread(_geoms(), build_patch(40.0), lambda _a: [], None, k=3)
    assert all(v is None for v in out.values())


@pytest.mark.neuron
@pytest.mark.slow
def test_spread_is_a_finite_well_formed_number_on_the_target():
    """End to end: the spread pipeline runs on a real scene and yields a finite,
    non-negative number rather than NaN, inf, or None.

    Deliberately NOT named "a real positive error bar": in this scene it is exactly
    0.0, and provably so — the next test pins why (one driven electrode's field is
    rotationally symmetric about z, and the target sits on that axis, so every
    jittered axon traces a congruent path). The old name and docstring claimed the
    jitter "really does move the threshold", which is false here, and the `>= 0.0`
    assertion passed on the zero without ever checking it. A test that measures 0.0
    while its name promises a positive error bar overstates what is validated.
    """
    from app.scene import build_patch
    from engine.spec import HomogeneousConductivity
    from engine.study.geometry_sweep import monopolar_center

    geoms = [ArrayGeometry(diameter_um=10.0, pitch_um=40.0, arrangement="hex", aperture_um=0.0)]
    out = geometry_trajectory_spread(
        geoms,
        build_patch(40.0),
        lambda a: monopolar_center(a, phase_width_us=200.0),
        HomogeneousConductivity(sigma_S_per_m=1.0),
        k=3,
        jitter_deg=20.0,
    )
    spread = out[(10.0, 40.0)]
    assert spread is not None
    assert math.isfinite(spread)
    assert spread >= 0.0


@pytest.mark.neuron
def test_spread_is_exactly_zero_when_the_field_is_symmetric_about_the_target():
    """Not a bug — the physics. `trajectory_spread` rotates the axon about +z, and a
    single driven electrode's field IS rotationally symmetric about z. With the
    target sitting directly under it, every rotated axon traces a congruent path
    through a congruent field, so all K thresholds are identical and the spread is
    exactly 0.

    This pins the limitation the number has in the default study scene: the whisker
    is honest there, and uninformative. It only measures something when the cell sits
    off the axis of symmetry (or the protocol drives more than the centre).
    """
    from app.scene import build_patch
    from engine.spec import HomogeneousConductivity
    from engine.study.geometry_sweep import monopolar_center

    geoms = [ArrayGeometry(diameter_um=10.0, pitch_um=40.0, arrangement="hex", aperture_um=0.0)]
    out = geometry_trajectory_spread(
        geoms,
        build_patch(40.0),  # target at (0, 0, depth) — on the axis
        lambda a: monopolar_center(a, phase_width_us=200.0),
        HomogeneousConductivity(sigma_S_per_m=1.0),
        k=3,
        jitter_deg=20.0,
    )
    assert out[(10.0, 40.0)] == pytest.approx(0.0, abs=1e-9)
