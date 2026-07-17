"""The Validation trust panel (P7 S6).

Which published/physics reproductions currently pass. This is the **committed**
report CI regenerates — the API serves it, it never recomputes the science on
request, so a skeptical reader sees exactly what the test suite last proved.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..models import ValidationReport
from ..service import validation_report

router = APIRouter()


@router.get("/validation", response_model=ValidationReport)
def get_validation() -> ValidationReport:
    return validation_report()
