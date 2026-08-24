"""ConductivityModel: how the tissue conducts. Homogeneous or layered."""

from __future__ import annotations

from dataclasses import dataclass

from .conventions import SCHEMA_VERSION

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Layer:
    """One tissue slab, ordered from the epiretinal surface downward."""

    sigma_S_per_m: float
    thickness_um: float
    # Optional diagonal anisotropy (sigma_x, sigma_y, sigma_z). None = isotropic.
    # Retinal tissue is mildly anisotropic; the model allows it, defaults off.
    anisotropy: Vec3 | None = None


@dataclass(frozen=True)
class HomogeneousConductivity:
    """A single conductivity everywhere: the analytical-tier default."""

    sigma_S_per_m: float
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class LayeredConductivity:
    """Ordered conductivity slabs, needed once FEM models real tissue layers."""

    layers: tuple[Layer, ...]
    schema_version: int = SCHEMA_VERSION


# A discriminated union: any spec/field code accepts either concrete model.
ConductivityModel = HomogeneousConductivity | LayeredConductivity
