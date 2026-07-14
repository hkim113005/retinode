"""Physics property tests for the analytical field backend.

These assert the physics (1/r decay, symmetry, the insulating-boundary
condition, units against a hand calculation), not just that the code runs.
Superposition is included but labelled as a plumbing check.
"""

import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine import spec
from engine.field import (
    AnalyticalBackend,
    UnsupportedByBackend,
    current_vector,
    potential_mV,
)

SIGMA = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
COEF = 1.0e3 / (4.0 * math.pi * 1.0)  # mV/uA * um, for sigma = 1


def one_electrode(pos=(0.0, 0.0, 0.0), size=10.0) -> spec.ElectrodeArray:
    return spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=pos, shape="disk", size_um=size),)
    )


def qp(*points) -> np.ndarray:
    return np.array(points, dtype=float)


# --- shape, dtype, units ---------------------------------------------------


def test_shape_and_dtype():
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="a", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(id="b", pos_um=(30.0, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )
    a = AnalyticalBackend().transfer_matrix(array, SIGMA, qp((0.0, 0.0, 50.0), (10.0, 0.0, 50.0)))
    assert a.shape == (2, 2)  # (m query points, n electrodes)
    assert a.dtype == np.float64


def test_units_free_space_matches_hand_calculation():
    # Free space: A = 1e3 / (4*pi*sigma*r). At r = 100 um, sigma = 1: ~0.7958 mV/uA.
    a = AnalyticalBackend(use_images=False).transfer_matrix(
        one_electrode(), SIGMA, qp((0.0, 0.0, 100.0))
    )
    assert a[0, 0] == pytest.approx(COEF / 100.0)


def test_units_half_space_doubles_on_the_plane():
    # A source on the insulating plane radiates into half the space, so the
    # image doubles the potential: A = 1e3 / (2*pi*sigma*r).
    a = AnalyticalBackend().transfer_matrix(one_electrode(), SIGMA, qp((0.0, 0.0, 100.0)))
    assert a[0, 0] == pytest.approx(2.0 * COEF / 100.0)


# --- decay and symmetry ----------------------------------------------------


def test_inverse_r_decay():
    backend = AnalyticalBackend()
    a = backend.transfer_matrix(one_electrode(), SIGMA, qp((100.0, 0.0, 0.0), (200.0, 0.0, 0.0)))
    assert a[1, 0] / a[0, 0] == pytest.approx(0.5)  # doubling r halves the potential


def test_point_source_is_spherically_symmetric_in_free_space():
    backend = AnalyticalBackend(use_images=False)
    a = backend.transfer_matrix(
        one_electrode(),
        SIGMA,
        qp((100.0, 0.0, 0.0), (0.0, 100.0, 0.0), (0.0, 0.0, 100.0), (-100.0, 0.0, 0.0)),
    )
    assert np.allclose(a[:, 0], a[0, 0])


def test_monotonic_decrease_with_distance():
    backend = AnalyticalBackend()
    a = backend.transfer_matrix(
        one_electrode(),
        SIGMA,
        qp((50.0, 0.0, 0.0), (100.0, 0.0, 0.0), (200.0, 0.0, 0.0), (400.0, 0.0, 0.0)),
    )
    col = a[:, 0]
    assert np.all(np.diff(col) < 0)


def test_insulating_boundary_makes_field_mirror_symmetric():
    # The Neumann condition on the substrate plane: with the image, the field is
    # symmetric under z -> -z, so a point and its mirror get the same potential.
    array = one_electrode(pos=(0.0, 0.0, 30.0))
    images = AnalyticalBackend()
    a = images.transfer_matrix(array, SIGMA, qp((50.0, 0.0, 40.0), (50.0, 0.0, -40.0)))
    assert a[0, 0] == pytest.approx(a[1, 0])

    # Free space (no image) has no such symmetry for an off-plane source.
    free = AnalyticalBackend(use_images=False)
    b = free.transfer_matrix(array, SIGMA, qp((50.0, 0.0, 40.0), (50.0, 0.0, -40.0)))
    assert b[0, 0] != pytest.approx(b[1, 0])


# --- regularization, guard, superposition ----------------------------------


def test_near_field_is_regularized_not_singular():
    array = one_electrode(pos=(0.0, 0.0, 0.0), size=10.0)  # radius 5 um
    at_center = qp((0.0, 0.0, 0.0))

    a = AnalyticalBackend().transfer_matrix(array, SIGMA, at_center)
    assert np.isfinite(a[0, 0])
    assert a[0, 0] == pytest.approx(2.0 * COEF / 5.0)  # floored at the electrode radius

    with np.errstate(divide="ignore"):  # dividing by r = 0 is the point here
        singular = AnalyticalBackend(regularize=False).transfer_matrix(array, SIGMA, at_center)
    assert np.isinf(singular[0, 0])


def test_layered_conductivity_is_unsupported():
    layered = spec.LayeredConductivity(layers=(spec.Layer(sigma_S_per_m=1.0, thickness_um=50.0),))
    with pytest.raises(UnsupportedByBackend):
        AnalyticalBackend().transfer_matrix(one_electrode(), layered, qp((0.0, 0.0, 50.0)))


def test_superposition_is_linear():  # plumbing, not physics
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="a", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(id="b", pos_um=(30.0, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )
    a = AnalyticalBackend().transfer_matrix(array, SIGMA, qp((10.0, 0.0, 40.0), (20.0, 0.0, 40.0)))
    i1 = np.array([1.0, 0.0])
    i2 = np.array([0.0, -2.0])
    assert np.allclose(potential_mV(a, i1 + i2), potential_mV(a, i1) + potential_mV(a, i2))


# --- the field -> current handoff ------------------------------------------


def test_current_vector_and_potential_end_to_end():
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="c", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(id="r1", pos_um=(30.0, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )
    wf = spec.Waveform(phase_width_us=100.0, amplitude_scale_uA=2.0)
    config = spec.StimConfig.from_map({"c": -1.0, "r1": 1.0}, waveform=wf)

    i = current_vector(array, config)
    assert np.allclose(i, [-2.0, 2.0])  # weight * amplitude, in array order

    # Near the cathode (negative current), the extracellular potential is negative.
    a = AnalyticalBackend().transfer_matrix(array, SIGMA, qp((3.0, 0.0, 5.0)))
    ve = potential_mV(a, i)
    assert ve[0] < 0.0


# --- property-based: the free-space formula holds for all sigma, r ---------


@given(
    st.floats(min_value=0.1, max_value=5.0),
    st.floats(min_value=10.0, max_value=1000.0),
)
def test_free_space_matches_closed_form(sigma, distance):
    cond = spec.HomogeneousConductivity(sigma_S_per_m=sigma)
    backend = AnalyticalBackend(use_images=False, regularize=False)
    a = backend.transfer_matrix(one_electrode(), cond, qp((distance, 0.0, 0.0)))
    assert a[0, 0] == pytest.approx(1.0e3 / (4.0 * math.pi * sigma * distance))
