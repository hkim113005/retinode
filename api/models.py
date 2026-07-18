"""The typed view contract: Pydantic request/response models.

These mirror the pure data functions in ``app/views.py`` (``field_grid`` /
``scorecard_data``) — the fixed seam the React client renders against
(docs/phase-7-plan.md, D2). A parity test locks them to the same numbers the Dash
view produces.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ConductiveFaces = Literal["tip", "sides", "all"]


# --- 3D electrode body (the custom-shape UI path) ----------------------------------
# A body makes the driven electrode a solid protruding into the tissue. It is what
# takes an electrode off the analytical tier: the point source sees only ``pos_um``,
# so a bodied scene MUST be solved with FEM (the API routes it to the conda env). The
# variants mirror ``engine.spec`` bodies; ``kind`` is the discriminator.


class NoBody(BaseModel):
    """A flat 2D face on the array plane — the default, analytical-friendly."""

    kind: Literal["none"] = "none"


class HemisphereBody(BaseModel):
    kind: Literal["hemisphere"] = "hemisphere"
    radius_um: float = Field(10.0, gt=0)


class CylinderBody(BaseModel):
    kind: Literal["cylinder"] = "cylinder"
    radius_um: float = Field(5.0, gt=0)
    height_um: float = Field(30.0, gt=0)
    conductive_faces: ConductiveFaces = "all"


class FrustumBody(BaseModel):
    kind: Literal["frustum"] = "frustum"
    base_radius_um: float = Field(8.0, gt=0)
    top_radius_um: float = Field(2.0, gt=0)  # < base is a penetrating tip; > base widens
    height_um: float = Field(20.0, gt=0)
    conductive_faces: ConductiveFaces = "all"


class CadBodySpec(BaseModel):
    """An imported STEP/BREP solid, referenced by the id ``POST /cad`` returned. The
    gmsh load lives in the FEM env, so the id resolves to a file there, not here."""

    kind: Literal["cad"] = "cad"
    upload_id: str
    conductive_faces: ConductiveFaces = "all"


class CadUploadResponse(BaseModel):
    """The id ``POST /cad`` hands back for a stored solid, plus its original name."""

    upload_id: str
    filename: str


# Discriminated on ``kind`` so the client (and openapi-typescript) get a clean union.
BodySpec = NoBody | HemisphereBody | CylinderBody | FrustumBody | CadBodySpec


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
    # A 3D body shapes the driven electrode e0. Anything but ``none`` is FEM-only (the
    # analytical tier can't see geometry), so the score/field routes dispatch a bodied
    # scene to the conda env. ``overlap_policy`` governs a cell a penetrating body
    # reaches: reject (refuse) or displace (sever the in-metal compartments).
    body: BodySpec = Field(default_factory=NoBody, discriminator="kind")
    overlap_policy: Literal["reject", "displace"] = "reject"


class FieldGridResponse(BaseModel):
    """Ve (mV) on a square grid at the cell plane — the analytical field preview."""

    xs_um: list[float]
    ys_um: list[float]
    # (n, n), row-major over ys then xs. A cell is ``null`` where a 3D electrode body
    # occupies the cell plane — there is no extracellular potential inside metal, so
    # the FEM field has a hole there (the analytical preview is always fully populated).
    ve_mV: list[list[float | None]]
    vmax_mV: float  # symmetric colour limit, |Ve| max (>=0)


class MarkerBody(BaseModel):
    """The 3D shape an electrode marker carries, so the loupe can draw the true solid
    (not just its flat footprint). Dimensions are summarised to what the view needs:
    ``radius_um`` is the base/lateral radius, ``height_um`` the depth into the tissue
    (0 for a hemisphere — its radius is the depth), ``top_radius_um`` the frustum's tip.
    A CAD solid is drawn as its bounding cylinder."""

    kind: Literal["hemisphere", "cylinder", "frustum", "cad"]
    radius_um: float
    height_um: float = 0.0
    top_radius_um: float | None = None


class ElectrodeMarker(BaseModel):
    """An electrode's footprint on the field plane, for the overlay. ``body`` is present
    for a 3D electrode, so the loupe can render the solid rather than a flat disk."""

    x_um: float
    y_um: float
    radius_um: float
    body: MarkerBody | None = None


class CellMarker(BaseModel):
    """A soma position on the field plane; the target is drawn filled."""

    x_um: float
    y_um: float
    is_target: bool


class ScorecardResponse(BaseModel):
    """The evaluator's operating-window verdict. ``activated=False`` means the
    target never fired in the searched range and every other field is absent."""

    activated: bool
    # The off-target set this was scored against (``EvaluationResult.offtarget_hash``).
    # The engine REFUSES to compare two results across differing off-target sets --
    # see ``engine.eval.result.require_same_offtarget``; the selective window is only
    # comparable when both were measured against the same bystanders. The client
    # shows runs side by side, so it needs this to tell the user when two runs are
    # not comparable rather than let them read a difference that is a category error.
    offtarget_hash: str | None = None
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
    # The per-cell off-target thresholds behind ``off_min_uA``, and which cell set it.
    # The evaluator computes the whole vector (``PopulationThresholds``) and the
    # scorecard used to collapse it to its minimum — but "how far is the SECOND
    # bystander?" is a different design question from "how far is the nearest?", and
    # the answer was already paid for. ``limiting_off_id`` names the binding cell.
    off_target_thresholds_uA: dict[str, float] | None = None
    limiting_off_id: str | None = None


class ValidationReproduction(BaseModel):
    """One published/physics check the engine reproduces, and how it was measured."""

    name: str
    source: str
    passed: bool
    measured: str
    criterion: str
    note: str = ""


class ValidationReport(BaseModel):
    """The trust panel: which reproductions currently pass (master plan §15). This is
    the committed report CI regenerates — the app renders it, never recomputes it."""

    n_pass: int
    n_total: int
    reproductions: list[ValidationReproduction]


class SweepControls(SceneControls):
    """An amplitude sweep of the scene: who fires, at what current."""

    amp_min_uA: float = Field(1.0, gt=0)
    amp_max_uA: float = Field(200.0, gt=0)
    # capped: at ~2 cells this is n × 2 NEURON runs, so 60 is ~3× a scorecard — the
    # honest ceiling before this stops being a "seconds" job
    n_amplitudes: int = Field(24, ge=2, le=60)
    spacing: Literal["linear", "log"] = "linear"


class ActivationCurve(BaseModel):
    """One cell's response across the sweep's amplitude grid, aligned index-for-index
    with ``AmplitudeSweepResponse.amplitudes_uA``.

    Note there is deliberately no "activation fraction" here. The patch is a target
    plus its bystanders — a handful of cells — so a fraction would be a two- or
    three-level step function wearing the costume of a sigmoid. Per-cell traces are
    what the engine actually knows."""

    cell_id: str
    is_target: bool
    activated: list[bool]
    # where the earliest spike started at each amplitude ("soma" / "ais" / ...); None
    # where the cell did not fire. Soma-vs-axon initiation as current rises is the
    # axon-avoidance premise made visible, and it comes back free from each run.
    initiation_region: list[str | None]
    # the first grid amplitude at which this cell fires. GRID RESOLUTION, not a
    # threshold: the scorecard's bisection converges to a tolerance and is the
    # accurate number. Kept separate so the two are never confused.
    crossing_uA: float | None = None
    blocks: bool = False  # stops firing again at higher current (depolarization block)


class AmplitudeSweepResponse(BaseModel):
    amplitudes_uA: list[float]
    curves: list[ActivationCurve]


class StudyControls(BaseModel):
    """A geometry sweep: the diameter × pitch grid to explore, plus the patch it is
    scored on. Combos with ``pitch < diameter`` (which would overlap) are dropped."""

    diameters_um: list[float] = Field(default_factory=lambda: [8.0, 12.0, 16.0, 20.0])
    pitches_um: list[float] = Field(default_factory=lambda: [30.0, 40.0, 55.0, 70.0])
    arrangement: Literal["grid", "hex"] = "hex"
    # How many axon trajectories to sample per geometry for the threshold spread.
    # 1 = OFF, and off is the default: the spread costs K extra threshold searches
    # per geometry, so nobody pays for a whisker they did not ask for. A std needs
    # >= 2 samples, so k=1 yields `spread_uA=None` by construction.
    trajectory_k: int = Field(1, ge=1, le=7)
    trajectory_jitter_deg: float = Field(15.0, gt=0.0, le=90.0)
    aperture_um: float = Field(120.0, ge=0)
    phase_width_us: float = Field(200.0, gt=0)
    neighbor_um: float = Field(40.0, gt=0)
    sigma_S_per_m: float = Field(1.0, gt=0)


class StudyPoint(BaseModel):
    """One evaluated geometry on the selectivity-versus-cost plane."""

    diameter_um: float
    pitch_um: float
    cost_uA: float  # current to fire the target (its threshold)
    selectivity_uA: float  # the selective window above threshold
    safe: bool
    on_frontier: bool  # not beaten on both axes by another safe geometry
    # Std of the target threshold across sampled axon trajectories — the honest error
    # bar, since the true axon path is unknown (engine.study.spread). None means "not
    # measured" (trajectory_k=1, or the target did not fire on enough paths); it must
    # render as ABSENT, never as +/-0.
    spread_uA: float | None = None


class StudyResult(BaseModel):
    """A completed sweep: every activated geometry, and how many were swept."""

    points: list[StudyPoint]
    n_geometries: int


class JobStatus(BaseModel):
    """A background job's state, polled by the client. When ``status`` is ``"done"``,
    the matching result is present — ``scorecard`` for a score job, ``field`` (+
    ``max_divergence_pct`` vs the analytical preview) for an accurate-field job.
    ``cached`` means it was served from a prior identical run (P7 S3)."""

    id: str
    status: Literal["running", "done", "error"]
    fraction: float  # 0..1 progress
    message: str
    cached: bool = False
    scorecard: ScorecardResponse | None = None
    field: FieldGridResponse | None = None
    max_divergence_pct: float | None = None
    study: StudyResult | None = None
    sweep: AmplitudeSweepResponse | None = None
    error: str | None = None


class CompareResponse(BaseModel):
    """One configuration scored for the Compare screen: the field and its scene
    overlays always, the scorecard only when requested (it costs a threshold
    search). This is the field-view data contract — grid + electrode outlines +
    soma overlays (master plan §16)."""

    field: FieldGridResponse
    electrodes: list[ElectrodeMarker]
    cells: list[CellMarker]
    scorecard: ScorecardResponse | None = None
