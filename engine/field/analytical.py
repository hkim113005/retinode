"""Tier-1 analytical field backend: point sources in a homogeneous half-space.

The epiretinal array sits on an insulating substrate, so the free-space Green's
function ``I / (4*pi*sigma*r)`` is replaced by its method-of-images form: a
same-sign image across the substrate plane. That image enforces the insulating
(Neumann) boundary and, for a source on the plane, doubles the potential to
``I / (2*pi*sigma*r)``. This shapes the near field — which is where selectivity
lives — so it is not a cosmetic correction.

Only a homogeneous isotropic conductivity has this closed form; layered or
anisotropic models must use a FEM backend (raised as UnsupportedByBackend).

Units: A is returned in mV/uA (see spec/conventions.py), derived from SI by
mV/uA = 1e3 * V/A and r_m = 1e-6 * r_um, giving A[i,j] = 1e3 / (4*pi*sigma*r_um)
per source, so ``Ve[mV] = A @ I[uA]``.
"""

from __future__ import annotations

import math

import numpy as np

from engine.spec import ConductivityModel, ElectrodeArray, HomogeneousConductivity
from engine.spec.geometry import radius_um

from .backend import UnsupportedByBackend


class AnalyticalBackend:
    """Point/disk sources in a homogeneous half-space.

    - ``use_images``: enforce the insulating substrate plane by mirror images
      (default True). False gives the raw free-space field, for comparison.
    - ``boundary_plane_z_um``: the substrate plane (default 0).
    - ``regularize``: floor the source distance at the electrode radius so the
      near field is bounded rather than singular — a finite-electrode stand-in
      for the full equipotential-disk solution.
    """

    def __init__(
        self,
        *,
        use_images: bool = True,
        boundary_plane_z_um: float = 0.0,
        regularize: bool = True,
    ) -> None:
        self.name = "analytical"
        self.use_images = use_images
        self.boundary_plane_z_um = boundary_plane_z_um
        self.regularize = regularize

    def transfer_matrix(
        self,
        array: ElectrodeArray,
        conductivity: ConductivityModel,
        query_points_um: np.ndarray,
    ) -> np.ndarray:
        if not isinstance(conductivity, HomogeneousConductivity):
            raise UnsupportedByBackend(
                "analytical backend requires a homogeneous isotropic conductivity; "
                "use a FEM backend for layered/anisotropic models"
            )
        sigma = conductivity.sigma_S_per_m
        q = np.asarray(query_points_um, dtype=float).reshape(-1, 3)  # (m, 3)
        p = np.array([e.pos_um for e in array.electrodes], dtype=float).reshape(-1, 3)  # (n, 3)
        radii = np.array([radius_um(e) for e in array.electrodes], dtype=float)  # (n,)

        # coef / r_um yields mV/uA; see module docstring.
        coef = 1.0e3 / (4.0 * math.pi * sigma)
        a = coef / self._distances(q, p, radii)
        if self.use_images:
            p_img = p.copy()
            p_img[:, 2] = 2.0 * self.boundary_plane_z_um - p[:, 2]
            a = a + coef / self._distances(q, p_img, radii)
        return a

    def _distances(self, q: np.ndarray, p: np.ndarray, radii: np.ndarray) -> np.ndarray:
        r = np.linalg.norm(q[:, None, :] - p[None, :, :], axis=2)  # (m, n)
        if self.regularize:
            r = np.maximum(r, radii[None, :])
        return r
