"""Mesh-refinement convergence for the FEM field backend.

A single FEM number means nothing without evidence the mesh was fine enough to
resolve it. This module solves the transfer matrix on a base domain and on
progressively refined versions of it (``FieldDomain.refined``), and records how
much the sampled field changes between refinements. When the change between the
two finest meshes falls below a tolerance, the field has *converged*: the mesh is
no longer the thing setting the answer.

The convergence metric is the relative change of the whole transfer matrix at the
(fixed) query points between successive levels, ``||A_k - A_{k-1}|| / ||A_k||``,
i.e. how much the field the cable model would see still moves as the mesh sharpens.
The full curve (mesh size, field norm, relative change per level) is returned so
the convergence claim is auditable, not asserted.

The solver is injectable so the convergence *logic* is testable without dolfinx;
by default it calls :func:`engine.field.fem_fenicsx.solve_transfer_matrix`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from .mesh import FieldDomain

SolveFn = Callable[[FieldDomain], np.ndarray]


@dataclass(frozen=True)
class ConvergenceLevel:
    """One refinement level of a convergence study."""

    factor: float  # refinement applied to the base domain (1 = base, 2 = twice as fine)
    h_electrode_um: float  # the electrode mesh size at this level
    field_norm: float  # ||A|| at this level (the field magnitude the metric tracks)
    rel_change: float  # ||A - A_prev|| / ||A||; NaN at the first level (no predecessor)


@dataclass(frozen=True)
class ConvergenceReport:
    """The convergence curve plus the pass/fail against a tolerance."""

    levels: tuple[ConvergenceLevel, ...]
    tol: float

    @property
    def converged(self) -> bool:
        """True when the change between the two finest meshes is below ``tol``."""
        return len(self.levels) >= 2 and self.levels[-1].rel_change < self.tol

    @property
    def finest(self) -> ConvergenceLevel:
        return self.levels[-1]


def mesh_convergence(
    base_domain: FieldDomain,
    query_points_um: np.ndarray,
    *,
    factors: Sequence[float] = (1.0, 2.0, 4.0),
    tol: float = 0.02,
    degree: int = 1,
    solve: SolveFn | None = None,
) -> ConvergenceReport:
    """Solve on ``base_domain`` refined by each of ``factors`` (increasing → finer)
    and report the relative change of the transfer matrix between successive
    levels. ``solve(domain) -> A`` defaults to the DOLFINx backend; inject a stub
    to test the logic without a solver.

    The query points are fixed across levels (only the mesh changes), so the
    per-level ``rel_change`` measures pure discretization convergence of the field
    the cable model samples.
    """
    if len(factors) < 2:
        raise ValueError("need at least two refinement factors to measure convergence")
    if any(b <= a for a, b in zip(factors, factors[1:], strict=False)):
        raise ValueError("factors must be strictly increasing (each level finer than the last)")

    q = np.asarray(query_points_um, dtype=float).reshape(-1, 3)
    solver: SolveFn = solve or (lambda dom: _default_solver(dom, q, degree))

    levels: list[ConvergenceLevel] = []
    prev: np.ndarray | None = None
    for factor in factors:
        dom = base_domain.refined(factor)
        a = np.asarray(solver(dom), dtype=float)
        norm = float(np.linalg.norm(a))
        if prev is None:
            rel_change = math.nan
        elif norm > 0.0:
            rel_change = float(np.linalg.norm(a - prev) / norm)
        else:
            rel_change = math.nan
        levels.append(ConvergenceLevel(float(factor), dom.h_electrode_um, norm, rel_change))
        prev = a

    return ConvergenceReport(tuple(levels), tol)


def _default_solver(domain: FieldDomain, query_points_um: np.ndarray, degree: int) -> np.ndarray:
    # imported here so the module (and the injectable-logic path) load without dolfinx
    from .fem_fenicsx import solve_transfer_matrix

    return solve_transfer_matrix(domain, query_points_um, degree=degree)
