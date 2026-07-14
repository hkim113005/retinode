"""Build a NEURON RGC from a reconstructed SWC arbor + an appended axon.

The dendrites and soma come from a vendored reconstruction (see
`morphologies/PROVENANCE.md`), loaded via NEURON's Import3D. Retinal SWC
reconstructions rarely trace the axon, so the **axon hillock**, the
**sodium-channel band (AIS)** — where the spike initiates — and the intraretinal
**axon** are appended here. Channel densities and temperature are applied
separately (S2c, `channels.py`); this module builds geometry only.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import _neuron, swc

MORPHOLOGY_DIR = Path(__file__).resolve().parent / "morphologies"
_TEMPLATES = {
    "default": "20160506-P21-control38-1.CNG.swc",
    "ganglion": "20160506-P21-control38-1.CNG.swc",
}


def template_path(cell_type: str = "default") -> Path:
    return MORPHOLOGY_DIR / _TEMPLATES.get(cell_type, _TEMPLATES["default"])


@dataclass
class MorphologyParams:
    """Geometry of the appended axon (µm). Nominal; refined/validated in S5."""

    hillock_len_um: float = 10.0
    hillock_diam_um: float = 2.0
    ais_len_um: float = 40.0  # the sodium-channel band
    ais_diam_um: float = 1.0
    axon_diam_um: float = 1.0
    axon_len_um: float = 300.0


class RGCModel:
    """A single NEURON RGC: soma + dendrites (from SWC) + hillock/AIS/axon.

    All Sections are held on the instance so NEURON does not garbage-collect
    them. Region section lists are exposed via `regions()`.
    """

    # Assigned by Import3D's gui.instantiate(self) — SectionLists per region.
    soma: Any
    dend: Any

    def __init__(
        self,
        swc_path: str | Path,
        params: MorphologyParams | None = None,
    ) -> None:
        self.h: Any = _neuron.load()
        self.params = params or MorphologyParams()
        self._load_swc(swc_path)
        self._append_axon()

    def _load_swc(self, swc_path: str | Path) -> None:
        h = self.h
        h.load_file("import3d.hoc")
        cleaned = swc.strip_comments(Path(swc_path).read_text())
        tmp = tempfile.NamedTemporaryFile("w", suffix=".swc", delete=False)
        try:
            tmp.write(cleaned)
            tmp.close()
            reader = h.Import3d_SWC_read()
            reader.input(tmp.name)
            gui = h.Import3d_GUI(reader, 0)
            gui.instantiate(self)  # assigns self.soma, self.dend (SectionLists)
        finally:
            os.unlink(tmp.name)
        self.soma_sec = next(iter(self.soma))
        self.dendrite_secs = list(self.dend) if hasattr(self, "dend") else []

    def _soma_center_um(self) -> tuple[float, float, float]:
        s = self.soma_sec
        n = s.n3d()
        if n == 0:
            return (0.0, 0.0, 0.0)
        return (
            sum(s.x3d(i) for i in range(n)) / n,
            sum(s.y3d(i) for i in range(n)) / n,
            sum(s.z3d(i) for i in range(n)) / n,
        )

    def _append_axon(self) -> None:
        # Give the appended sections explicit 3D coordinates (pt3dadd), so the
        # extracellular field can be evaluated at them (S3) — the AIS especially,
        # since it is where the spike initiates. They run in +x from the soma
        # (in-plane, nominal); S6 lays them along the spec's axon_um path.
        h, p = self.h, self.params
        cx, cy, cz = self._soma_center_um()
        x = cx

        def add(name: str, length: float, diam: float, parent: Any) -> Any:
            nonlocal x
            sec = h.Section(name=name)
            sec.connect(parent(1.0))
            h.pt3dadd(x, cy, cz, diam, sec=sec)
            h.pt3dadd(x + length, cy, cz, diam, sec=sec)
            x = x + length
            return sec

        self.hillock = add("hillock", p.hillock_len_um, p.hillock_diam_um, self.soma_sec)
        self.ais = add("ais", p.ais_len_um, p.ais_diam_um, self.hillock)  # sodium band
        self.axon = add("axon", p.axon_len_um, p.axon_diam_um, self.ais)

    def regions(self) -> dict[str, list[Any]]:
        return {
            "soma": [self.soma_sec],
            "dendrite": list(self.dendrite_secs),
            "hillock": [self.hillock],
            "ais": [self.ais],
            "axon": [self.axon],
        }

    def all_sections(self) -> list[Any]:
        return [sec for secs in self.regions().values() for sec in secs]

    def total_length_um(self) -> float:
        return sum(sec.L for sec in self.all_sections())


def build_rgc(cell_type: str = "default", params: MorphologyParams | None = None) -> RGCModel:
    """Build the RGC for a cell type from its template morphology."""
    return RGCModel(template_path(cell_type), params=params)
