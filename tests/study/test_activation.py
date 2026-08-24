"""P8: the amplitude sweep. The curve the threshold search throws away.

The grid maths and the curve readers are pure, so they are tested without NEURON.
The end-to-end sweep is marked `neuron` and lives at the bottom.
"""

import math

import pytest

from engine.study.activation import CellActivation, amplitude_grid


def _cell(activated, *, cell_id="target", is_target=True):
    return CellActivation(
        cell_id=cell_id,
        is_target=is_target,
        activated=tuple(activated),
        initiation_region=tuple(None for _ in activated),
    )


class TestAmplitudeGrid:
    def test_linear_spans_the_range_inclusive(self):
        assert amplitude_grid(1.0, 5.0, 5) == (1.0, 2.0, 3.0, 4.0, 5.0)

    def test_log_resolves_the_low_end_where_thresholds_live(self):
        g = amplitude_grid(1.0, 100.0, 3, spacing="log")
        assert g[0] == pytest.approx(1.0)
        assert g[1] == pytest.approx(10.0)  # geometric middle, not 50
        assert g[2] == pytest.approx(100.0)

    def test_rejects_a_range_that_cannot_be_swept(self):
        with pytest.raises(ValueError):
            amplitude_grid(0.0, 10.0, 5)  # zero amplitude is not a stimulus
        with pytest.raises(ValueError):
            amplitude_grid(10.0, 1.0, 5)  # backwards
        with pytest.raises(ValueError):
            amplitude_grid(1.0, 10.0, 1)  # one point is not a curve


class TestCrossing:
    AMPS = (1.0, 2.0, 3.0, 4.0)

    def test_reports_the_first_firing_amplitude(self):
        assert _cell([False, False, True, True]).crossing_uA(self.AMPS) == 3.0

    def test_is_none_when_the_cell_never_fires(self):
        assert _cell([False] * 4).crossing_uA(self.AMPS) is None

    def test_is_the_grid_point_not_an_interpolation(self):
        # deliberately coarser than the bisection's tolerance: these are different
        # numbers and must not be conflated
        assert _cell([False, True, True, True]).crossing_uA(self.AMPS) == 2.0


class TestBlock:
    def test_detects_a_cell_that_stops_firing_again(self):
        # depolarization block: on, then off at higher current
        assert _cell([False, True, True, False]).blocks() is True

    def test_a_plain_monotonic_cell_does_not_block(self):
        assert _cell([False, False, True, True]).blocks() is False

    def test_a_silent_cell_does_not_block(self):
        assert _cell([False] * 4).blocks() is False

    def test_block_is_reported_even_if_it_recovers(self):
        assert _cell([True, False, True]).blocks() is True


@pytest.mark.neuron
def test_amplitude_sweep_recovers_the_threshold_it_brackets():
    """The curve and the bisection must agree: the first firing grid point sits at or
    just above the searched threshold, never below it."""
    from app.scene import build_scene
    from engine.cable.population import population_thresholds
    from engine.study.activation import amplitude_sweep

    s = build_scene(
        layout="single", electrode_um=10.0, pitch_um=60.0,
        phase_width_us=200.0, neighbor_um=40.0, sigma_S_per_m=1.0,
    )
    thr = population_thresholds(s.patch, s.array, s.config, s.conductivity)
    assert thr.target_threshold_uA is not None

    amps = amplitude_grid(1.0, 120.0, 25)
    seen: list[int] = []
    sweep = amplitude_sweep(
        s.patch, s.array, s.config, s.conductivity,
        amplitudes_uA=amps,
        on_amplitude=lambda i, _a: seen.append(i),
    )

    assert sweep.amplitudes_uA == amps
    assert seen == list(range(len(amps)))  # progress fires once per column, in order
    assert len(sweep.cells) >= 2  # target + at least the neighbour
    assert sweep.cells[0].is_target
    assert all(len(c.activated) == len(amps) for c in sweep.cells)

    crossing = sweep.cells[0].crossing_uA(amps)
    assert crossing is not None
    step = amps[1] - amps[0]
    # the grid crossing brackets the searched threshold from above, within one step
    assert thr.target_threshold_uA <= crossing + 1e-9
    assert crossing - thr.target_threshold_uA <= step + 1e-9


@pytest.mark.neuron
def test_the_target_fires_before_the_bystander():
    """The whole premise of the tool, read straight off the curve."""
    from app.scene import build_scene
    from engine.study.activation import amplitude_sweep

    s = build_scene(
        layout="single", electrode_um=10.0, pitch_um=60.0,
        phase_width_us=200.0, neighbor_um=40.0, sigma_S_per_m=1.0,
    )
    amps = amplitude_grid(1.0, 200.0, 30)
    sweep = amplitude_sweep(s.patch, s.array, s.config, s.conductivity, amplitudes_uA=amps)
    target = next(c for c in sweep.cells if c.is_target)
    offs = [c for c in sweep.cells if not c.is_target]

    t = target.crossing_uA(amps)
    assert t is not None
    for off in offs:
        o = off.crossing_uA(amps)
        if o is not None:
            assert t <= o, f"{off.cell_id} fired before the target"
        assert math.isfinite(t)


def test_amplitude_sweep_rejects_an_empty_grid():
    """The empty-grid guard fires before any field solve, so it is fast-testable,
    but every other amplitude_sweep test is neuron-marked, so this cheap branch was
    never hit."""
    from engine.study.activation import amplitude_sweep

    with pytest.raises(ValueError, match="at least one amplitude"):
        amplitude_sweep(None, None, None, None, amplitudes_uA=[])
