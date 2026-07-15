"""P3 S4: the validation report serializes and counts correctly (fast)."""

from engine.validate.report import report_dict
from engine.validate.reproduction import Reproduction


def test_report_dict_counts_and_serializes():
    reps = [
        Reproduction("a", "src", True, "measured a", "crit"),
        Reproduction("b", "src", False, "measured b", "crit", note="deferred"),
    ]
    d = report_dict(reps)
    assert d["n_total"] == 2 and d["n_pass"] == 1
    first = d["reproductions"][0]
    assert first["name"] == "a" and first["passed"] is True
    assert set(first) >= {"name", "source", "passed", "measured", "criterion", "note"}
    assert d["reproductions"][1]["note"] == "deferred"
