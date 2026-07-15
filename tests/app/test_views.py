"""P2b: the view data contract — field grid, figure, and scorecard payload."""

from app.scene import build_scene
from app.views import field_figure, field_grid, scorecard_data
from engine.cable.population import PopulationThresholds
from engine.eval import evaluate


def _scene():
    return build_scene(
        layout="single",
        electrode_um=10.0,
        pitch_um=60.0,
        phase_width_us=200.0,
        neighbor_um=40.0,
        sigma_S_per_m=1.0,
    )


def _result(target_uA, off):
    def provider(patch, array, config, conductivity, *, off_target_set=None, backend=None):
        return PopulationThresholds(patch.target_id, target_uA, dict(off))

    s = _scene()
    return evaluate(s.patch, s.array, s.config, s.conductivity, thresholds_provider=provider)


def test_field_grid_is_square_and_cathodic_negative():
    s = _scene()
    g = field_grid(s.array, s.config, s.conductivity, n=41)
    assert g.ve_mV.shape == (41, 41) and g.xs.shape == (41,)
    # a single cathode makes Ve negative, deepest under the electrode (grid centre)
    assert g.ve_mV.max() <= 0.0
    assert g.ve_mV[20, 20] == g.ve_mV.min()


def test_field_figure_has_heatmap_plus_cell_markers():
    s = _scene()
    fig = field_figure(s.array, s.config, s.conductivity, s.patch)
    assert len(fig.data) == 3
    assert fig.data[0].type == "heatmap"
    assert fig.data[1].type == "scatter" and fig.data[2].type == "scatter"


def test_scorecard_data_for_a_usable_window():
    d = scorecard_data(_result(8.0, {"neighbor": 12.0}))
    assert d["activated"] and d["usable"]
    assert d["target_uA"] == 8.0
    assert d["off_min_uA"] == 12.0
    assert d["ratio"] == 1.5
    assert d["limiting"] == "off_target"


def test_scorecard_data_for_no_activation():
    assert scorecard_data(_result(None, {"neighbor": 12.0})) == {"activated": False}
