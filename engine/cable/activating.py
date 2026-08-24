"""Rattay's activating function: a diagnostic for where an axon is driven to fire.

To first order, an axon is driven toward firing where the second spatial
derivative of the extracellular potential along it is positive (Rattay 1986):
``AF ∝ ∂²Ve/∂s²``. Bi-electrode patterns that flatten this along a bundle are how
axon avoidance works (Vilkhu 2021). This returns ∂²Ve/∂s² (mV/µm²) at each axon
compartment. Only the sign and shape carry meaning here: the positive cable
prefactor is dropped. Endpoints, where a centered second derivative is
undefined, are 0.
"""

from __future__ import annotations

import numpy as np


def activating_function(
    axon_um: np.ndarray,
    ve_mV: np.ndarray,
) -> np.ndarray:
    """Second derivative of Ve with respect to arc length along the axon path."""
    p = np.asarray(axon_um, dtype=float).reshape(-1, 3)
    v = np.asarray(ve_mV, dtype=float).reshape(-1)
    if p.shape[0] != v.shape[0]:
        raise ValueError("axon points and Ve samples must have equal length")

    n = p.shape[0]
    af = np.zeros(n, dtype=float)
    if n < 3:
        return af

    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)  # spacing between points
    h1, h2 = seg[:-1], seg[1:]
    valid = (h1 > 0.0) & (h2 > 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        interior = 2.0 / (h1 + h2) * ((v[2:] - v[1:-1]) / h2 - (v[1:-1] - v[:-2]) / h1)
    af[1:-1] = np.where(valid, interior, 0.0)
    return af
