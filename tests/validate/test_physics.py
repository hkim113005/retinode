"""P3 S4: field-physics reproductions for the validation report (fast)."""

from engine.validate import physics


def test_reciprocity_holds():
    r = physics.reciprocity_holds()
    assert r.passed
    assert "G(a,b)" in r.measured


def test_far_field_decay():
    r = physics.far_field_decay()
    assert r.passed  # monopole ~1/r, dipole ~1/r^2
    assert "monopole" in r.measured and "dipole" in r.measured
