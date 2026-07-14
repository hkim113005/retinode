"""Pure-Python SWC parsing and region classification (no NEURON).

SWC is the standard neuron-morphology skeleton: one node per line as
``id type x y z radius parent``, with type codes 1=soma, 2=axon, 3=(basal)
dendrite, 4=apical dendrite. This module parses the file and classifies nodes
into the regions the cable engine cares about (soma / dendrite / axon), so the
topology can be tested without importing NEURON.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

Vec3 = tuple[float, float, float]

# SWC type code -> region. Apical and basal dendrites both count as "dendrite"
# for an RGC; anything unexpected is "other".
_REGION = {1: "soma", 2: "axon", 3: "dendrite", 4: "dendrite"}


@dataclass(frozen=True)
class SWCNode:
    id: int
    type: int
    x: float
    y: float
    z: float
    radius: float
    parent: int  # -1 for the root


def region_of(type_code: int) -> str:
    return _REGION.get(type_code, "other")


def parse(text: str) -> tuple[SWCNode, ...]:
    """Parse SWC text, skipping comment (``#``) and blank lines."""
    nodes: list[SWCNode] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        p = s.split()
        if len(p) < 7:
            continue
        nodes.append(
            SWCNode(
                id=int(float(p[0])),
                type=int(float(p[1])),
                x=float(p[2]),
                y=float(p[3]),
                z=float(p[4]),
                radius=float(p[5]),
                parent=int(float(p[6])),
            )
        )
    return tuple(nodes)


def load(path: str | Path) -> tuple[SWCNode, ...]:
    return parse(Path(path).read_text())


def strip_comments(text: str) -> str:
    """SWC with comment/blank lines removed (Import3D dislikes the CNG header)."""
    return "\n".join(
        s for line in text.splitlines() if (s := line.strip()) and not s.startswith("#")
    )


def counts_by_region(nodes: tuple[SWCNode, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for n in nodes:
        counts[region_of(n.type)] = counts.get(region_of(n.type), 0) + 1
    return counts


def soma_center_um(nodes: tuple[SWCNode, ...]) -> Vec3:
    soma = [n for n in nodes if n.type == 1]
    if not soma:
        raise ValueError("SWC has no soma nodes")
    n = len(soma)
    return (
        sum(s.x for s in soma) / n,
        sum(s.y for s in soma) / n,
        sum(s.z for s in soma) / n,
    )
