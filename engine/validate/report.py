"""Run the validation reproductions and write a JSON report (P3 S4).

The app reads this committed report and renders the Validation panel instantly;
CI's neuron job independently asserts the reproductions still pass, so the panel
is a snapshot of a gated result, not an unchecked claim. The numbers are
deterministic (fixed search parameters), so regenerating does not churn the file.

Regenerate (needs the ``cable`` extra) with::

    uv run python -m engine.validate.report
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .reproduction import Reproduction

REPORT_PATH = Path(__file__).resolve().parents[2] / "app" / "validation_report.json"


def run_all() -> list[Reproduction]:
    """Every validation reproduction — field physics, single cell, and selectivity."""
    from engine.cable.channels import build_active_rgc

    from . import axon_avoidance, nonlinearity, physics, selectivity, single_cell

    reps: list[Reproduction] = list(physics.all_physics_reproductions())

    cell = build_active_rgc()
    reps += single_cell.all_reproductions(cell)

    reps.append(selectivity.local_return_sharpens_the_field())
    reps.append(axon_avoidance.confined_return_flattens_axon_af())

    axon_cell = build_active_rgc(origin_um=(-200.0, 40.0, -20.0), axon_direction=(1.0, 0.0, 0.0))
    reps.append(axon_avoidance.confined_return_avoids_axon_of_passage(axon_cell))

    summ_cell = build_active_rgc(origin_um=(0.0, 0.0, -20.0), axon_direction=(0.0, -1.0, 0.0))
    reps.append(nonlinearity.subthreshold_electrodes_summate(summ_cell))
    return reps


def report_dict(reps: list[Reproduction]) -> dict:
    return {
        "n_pass": sum(r.passed for r in reps),
        "n_total": len(reps),
        "reproductions": [dataclasses.asdict(r) for r in reps],
    }


def write_report(path: Path = REPORT_PATH) -> Path:
    path.write_text(json.dumps(report_dict(run_all()), indent=2, ensure_ascii=False) + "\n")
    return path


if __name__ == "__main__":
    written = write_report()
    print(f"wrote {written}")
