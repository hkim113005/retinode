"""Fast (no-NEURON) SWC parsing and region classification."""

from engine.cable import swc
from engine.cable.morphology import template_path


def test_parse_vendored_rgc_regions():
    nodes = swc.load(template_path("default"))
    counts = swc.counts_by_region(nodes)
    assert counts["soma"] == 3  # standard 3-point soma
    assert counts["dendrite"] == 1514
    assert "axon" not in counts  # no axon traced; morphology.py appends it


def test_soma_center_near_origin():
    x, y, z = swc.soma_center_um(swc.load(template_path("default")))
    assert abs(x) < 1.0 and abs(y) < 1.0 and abs(z) < 1.0


def test_region_of_maps_both_dendrite_types():
    assert swc.region_of(1) == "soma"
    assert swc.region_of(2) == "axon"
    assert swc.region_of(3) == "dendrite"
    assert swc.region_of(4) == "dendrite"  # apical folds into dendrite
    assert swc.region_of(7) == "other"


def test_comments_and_blank_lines_are_skipped():
    text = "# header\n\n 1 1 0 0 0 1 -1\n2 3 1 0 0 0.5 1\n#c\n"
    assert swc.strip_comments(text) == "1 1 0 0 0 1 -1\n2 3 1 0 0 0.5 1"
    nodes = swc.parse(text)
    assert len(nodes) == 2
    assert nodes[0].type == 1 and nodes[1].parent == 1
