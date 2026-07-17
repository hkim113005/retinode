"""The typed view contract: Pydantic request/response models.

These mirror the pure data functions in ``app/views.py`` (``field_grid`` /
``scorecard_data``) — the fixed seam the React client renders against
(docs/phase-7-plan.md, D2). A parity test locks them to the same numbers the Dash
view produces.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SceneControls(BaseModel):
    """The Compare screen's inputs — the same handful of controls the Dash app
    exposes, translated to specs server-side via ``app.scene.build_scene``."""

    layout: Literal["single", "bipolar"] = "single"
    electrode_um: float = Field(10.0, gt=0)
    pitch_um: float = Field(60.0, gt=0)
    phase_width_us: float = Field(200.0, gt=0)
    neighbor_um: float = Field(40.0, gt=0)
    sigma_S_per_m: float = Field(1.0, gt=0)
    # field-preview options
    extent_um: float = Field(130.0, gt=0)
    n: int = Field(61, ge=9, le=257)
    # the operating-window scorecard needs NEURON thresholds, so it is opt-in; the
    # field preview stays synchronous and NEURON-free (D3). S3 moves this to a job.
    include_scorecard: bool = False


class FieldGridResponse(BaseModel):
    """Ve (mV) on a square grid at the cell plane — the analytical field preview."""

    xs_um: list[float]
    ys_um: list[float]
    ve_mV: list[list[float]]  # (n, n), row-major over ys then xs
    vmax_mV: float  # symmetric colour limit, |Ve| max (>=0)


class ScorecardResponse(BaseModel):
    """The evaluator's operating-window verdict. ``activated=False`` means the
    target never fired in the searched range and every other field is absent."""

    activated: bool
    target_uA: float | None = None
    off_min_uA: float | None = None
    ratio: float | None = None
    window_lo_uA: float | None = None
    window_hi_uA: float | None = None
    usable_margin_uA: float | None = None
    usable: bool | None = None
    limiting: str | None = None
    safety_ceiling_uA: float | None = None
    safe_at_target: bool | None = None


class CompareResponse(BaseModel):
    """One configuration scored for the Compare screen: the field always, the
    scorecard only when requested (it costs a threshold search)."""

    field: FieldGridResponse
    scorecard: ScorecardResponse | None = None
