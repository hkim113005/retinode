"""Analytical-vs-FEM regime map: where can the cheap tier be trusted?

The analytical backend is a homogeneous half-space; the retina is layered. So for
any layered medium there is an error in pretending it is homogeneous, and the
question the evaluator needs answered is *how big*, as a function of the layer
contrast. This module sweeps the contrast ``sigma2/sigma1``, solves the true
(FEM, layered) field and the analytical (homogeneous-sigma1) field at the same
query points, and records the relative error and whether it is within a tolerance.

The result is a small map the app/evaluator consults: at low contrast the
analytical tier is trustworthy (cheap, instant); past some contrast the error
crosses the tolerance and the field must be escalated to FEM. At contrast 1 the
medium *is* homogeneous, so the error collapses to the FEM/analytical
discretization floor, a built-in sanity check on the map itself.

The solvers are injectable so the map's *logic* is testable without a solver; by
default the FEM side is :func:`engine.field.fem_fenicsx.solve_transfer_matrix` and
the analytical side is :class:`engine.field.analytical.AnalyticalBackend`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from engine.spec import ElectrodeArray, HomogeneousConductivity, LayeredConductivity
from engine.spec.conductivity import Layer

from .mesh import FieldDomain

FemSolveFn = Callable[[FieldDomain], np.ndarray]
AnalyticalSolveFn = Callable[[], np.ndarray]


@dataclass(frozen=True)
class RegimePoint:
    """The analytical approximation's error at one layer contrast."""

    contrast: float  # sigma2 / sigma1 (buried layer relative to the surface layer)
    rel_error: float  # ||A_fem_layered - A_analytical_sigma1|| / ||A_fem||
    trustworthy: bool  # rel_error < tol -> the analytical tier is safe to use here


@dataclass(frozen=True)
class RegimeMap:
    """The error curve over contrast, plus the tolerance that defines 'trustworthy'."""

    points: tuple[RegimePoint, ...]
    tol: float

    @property
    def trustworthy_contrasts(self) -> tuple[float, ...]:
        return tuple(p.contrast for p in self.points if p.trustworthy)

    def trustworthy_at(self, contrast: float) -> bool:
        """Whether the analytical tier is trustworthy at ``contrast``, judged by
        the nearest sampled point (the map is meant to be sampled densely enough
        that the nearest point is representative)."""
        nearest = min(self.points, key=lambda p: abs(p.contrast - contrast))
        return nearest.trustworthy


def analytical_error(a_fem: np.ndarray, a_analytical: np.ndarray) -> float:
    """Relative error of the analytical field against the FEM field (the truth),
    ``||A_fem - A_an|| / ||A_fem||``. 0 when they coincide."""
    a_fem = np.asarray(a_fem, dtype=float)
    a_an = np.asarray(a_analytical, dtype=float)
    denom = float(np.linalg.norm(a_fem))
    if denom == 0.0:
        return float("nan")
    return float(np.linalg.norm(a_fem - a_an) / denom)


def regime_map(
    array: ElectrodeArray,
    query_points_um: np.ndarray,
    *,
    sigma1_S_per_m: float,
    contrasts: Sequence[float],
    layer_thickness_um: float,
    half_width_um: float,
    depth_um: float,
    h_electrode_um: float,
    h_far_um: float,
    tol: float = 0.1,
    degree: int = 1,
    solve_fem: FemSolveFn | None = None,
    solve_analytical: AnalyticalSolveFn | None = None,
) -> RegimeMap:
    """Sweep ``contrasts`` (each ``sigma2/sigma1``), comparing the FEM layered
    field to the analytical homogeneous-``sigma1`` field at ``query_points_um``.

    The analytical field is the same for every contrast (it always ignores the
    buried layer), so it is computed once. ``solve_fem(domain) -> A`` and
    ``solve_analytical() -> A`` default to the real backends; inject stubs to test
    the sweep logic without a solver.
    """
    q = np.asarray(query_points_um, dtype=float).reshape(-1, 3)

    analytical: AnalyticalSolveFn = solve_analytical or (
        lambda: _default_analytical(array, sigma1_S_per_m, q)
    )
    fem: FemSolveFn = solve_fem or (lambda dom: _default_fem(dom, q, degree))

    a_analytical = np.asarray(analytical(), dtype=float)

    points: list[RegimePoint] = []
    for contrast in contrasts:
        cond = LayeredConductivity(
            layers=(
                Layer(sigma1_S_per_m, layer_thickness_um),
                Layer(sigma1_S_per_m * contrast, depth_um - layer_thickness_um),
            )
        )
        dom = FieldDomain(array, cond, half_width_um, depth_um, h_electrode_um, h_far_um)
        err = analytical_error(fem(dom), a_analytical)
        points.append(RegimePoint(float(contrast), err, err < tol))

    return RegimeMap(tuple(points), tol)


def _default_analytical(
    array: ElectrodeArray, sigma1_S_per_m: float, query_points_um: np.ndarray
) -> np.ndarray:
    from .analytical import AnalyticalBackend

    return AnalyticalBackend().transfer_matrix(
        array, HomogeneousConductivity(sigma1_S_per_m), query_points_um
    )


def _default_fem(domain: FieldDomain, query_points_um: np.ndarray, degree: int) -> np.ndarray:
    from .fem_fenicsx import solve_transfer_matrix

    return solve_transfer_matrix(domain, query_points_um, degree=degree)
