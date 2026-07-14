"""Edge cases and additional physics for the analytical field backend."""

import numpy as np
import pytest

from engine import spec
from engine.field import AnalyticalBackend, current_vector, potential_mV

SIGMA = spec.HomogeneousConductivity(sigma_S_per_m=1.0)


def one_electrode(pos=(0.0, 0.0, 0.0), size=10.0) -> spec.ElectrodeArray:
    return spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=pos, shape="disk", size_um=size),)
    )


def qp(*points) -> np.ndarray:
    return np.array(points, dtype=float)


# --- degenerate shapes -----------------------------------------------------


def test_empty_array_gives_zero_width_matrix():
    a = AnalyticalBackend().transfer_matrix(
        spec.ElectrodeArray(electrodes=()), SIGMA, qp((0.0, 0.0, 50.0))
    )
    assert a.shape == (1, 0)


def test_empty_query_points_give_zero_height_matrix():
    a = AnalyticalBackend().transfer_matrix(one_electrode(), SIGMA, np.empty((0, 3)))
    assert a.shape == (0, 1)


# --- physics invariants ----------------------------------------------------


def test_potential_is_positive_everywhere_for_a_source():
    q = qp((10.0, 0.0, 5.0), (0.0, 50.0, -30.0), (-100.0, 20.0, 200.0), (0.0, 0.0, -10.0))
    a = AnalyticalBackend().transfer_matrix(one_electrode(pos=(0.0, 0.0, 20.0)), SIGMA, q)
    assert np.all(a > 0.0)


def test_potential_scales_inversely_with_conductivity():
    q = qp((0.0, 0.0, 100.0))
    a1 = AnalyticalBackend().transfer_matrix(
        one_electrode(), spec.HomogeneousConductivity(sigma_S_per_m=1.0), q
    )
    a2 = AnalyticalBackend().transfer_matrix(
        one_electrode(), spec.HomogeneousConductivity(sigma_S_per_m=2.0), q
    )
    assert np.allclose(a2, 0.5 * a1)


def test_images_equal_twice_free_space_for_on_plane_source():
    q = qp((30.0, 10.0, 60.0), (0.0, 0.0, 100.0), (-40.0, 5.0, -25.0))
    array = one_electrode(pos=(0.0, 0.0, 0.0))  # source on the plane
    a_img = AnalyticalBackend(use_images=True).transfer_matrix(array, SIGMA, q)
    a_free = AnalyticalBackend(use_images=False).transfer_matrix(array, SIGMA, q)
    assert np.allclose(a_img, 2.0 * a_free)


def test_greens_function_is_reciprocal():
    # G(source at p, field at q) == G(source at q, field at p), with images.
    p, r = (0.0, 0.0, 50.0), (30.0, 0.0, 20.0)
    backend = AnalyticalBackend()
    a_pr = backend.transfer_matrix(one_electrode(pos=p), SIGMA, qp(r))
    a_rp = backend.transfer_matrix(one_electrode(pos=r), SIGMA, qp(p))
    assert a_pr[0, 0] == pytest.approx(a_rp[0, 0])


def test_in_plane_translation_invariance():
    backend = AnalyticalBackend()
    base = backend.transfer_matrix(
        one_electrode(pos=(0.0, 0.0, 30.0)), SIGMA, qp((50.0, 0.0, 40.0))
    )
    shifted = backend.transfer_matrix(
        one_electrode(pos=(100.0, -20.0, 30.0)), SIGMA, qp((150.0, -20.0, 40.0))
    )
    assert base[0, 0] == pytest.approx(shifted[0, 0])


def test_dipole_far_field_decays_faster_than_monopole():
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="p", pos_um=(5.0, 0.0, 0.0), shape="disk", size_um=4.0),
            spec.Electrode(id="n", pos_um=(-5.0, 0.0, 0.0), shape="disk", size_um=4.0),
        )
    )
    far = qp((10000.0, 0.0, 0.0), (20000.0, 0.0, 0.0))
    a = AnalyticalBackend().transfer_matrix(array, SIGMA, far)
    dipole = np.abs(potential_mV(a, np.array([1.0, -1.0])))
    monopole = np.abs(potential_mV(a, np.array([1.0, 0.0])))
    # Monopole falls as 1/r (ratio ~0.5); the dipole falls as ~1/r^2 (ratio ~0.25).
    assert monopole[1] / monopole[0] == pytest.approx(0.5, rel=1e-3)
    assert dipole[1] / dipole[0] < 0.3


# --- current handoff edges -------------------------------------------------


def test_current_vector_drops_unknown_and_zeros_empty():
    array = one_electrode()  # a single electrode "e"
    wf = spec.Waveform(phase_width_us=100.0, amplitude_scale_uA=3.0)
    # A ghost weight not in the array is silently dropped here (validate_scene
    # is what flags it as unknown-electrode).
    driven = spec.StimConfig.from_map({"e": -1.0, "ghost": 2.0}, waveform=wf, distant_return=True)
    assert np.allclose(current_vector(array, driven), [-3.0])
    assert np.allclose(current_vector(array, spec.StimConfig.from_map({}, waveform=wf)), [0.0])
