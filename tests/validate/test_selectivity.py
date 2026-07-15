"""P3 S1: Fan 2019 local-return field-sharpening reproduction (fast, no NEURON)."""

from engine.validate.selectivity import local_return_sharpens_the_field


def test_local_return_sharpens_the_field():
    r = local_return_sharpens_the_field()
    assert r.passed  # local-return field-selectivity exceeds monopolar
    assert r.source == "Fan et al. 2019"
    assert "monopolar" in r.measured and "local return" in r.measured
    # the honest scope note is recorded (threshold-level gain deferred to Phase 4)
    assert "Phase 4" in r.note
