"""P2 S2: the Project ties specs, fields, results, and manifest into one workspace."""

import numpy as np

from engine import spec
from engine.store.project import PROJECT_SCHEMA_VERSION, Project


def test_open_creates_the_layout_and_manifest(tmp_path):
    root = tmp_path / "proj.retinode"
    p = Project.open(root)
    assert (root / "specs").is_dir()
    assert (root / "cache" / "fields").is_dir()
    assert (root / "results").is_dir()
    m = p.manifest()
    assert m["schema_version"] == PROJECT_SCHEMA_VERSION
    assert "created" in m and "updated" in m


def test_result_round_trip_and_cache_hit(tmp_path, result_windowed):
    p = Project.open(tmp_path / "proj")
    r = result_windowed
    assert not p.has_result(r.result_key)  # a miss the sweep would solve
    p.put_result(r)
    assert p.has_result(r.result_key)  # now a cache hit it can skip
    assert p.get_result(r.result_key) == r


def test_field_round_trip(tmp_path):
    p = Project.open(tmp_path / "proj")
    a = np.array([[1.0, 2.0], [3.0, 4.0]])
    assert not p.has_field("k1") and p.get_field("k1") is None
    p.put_field("k1", a, backend_name="analytical")
    assert p.has_field("k1")
    assert np.array_equal(p.get_field("k1"), a)


def test_spec_round_trip_by_hash(tmp_path):
    p = Project.open(tmp_path / "proj")
    array = spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )
    h = p.put_spec(array)
    assert p.get_spec(h) == array
    assert p.get_spec("0" * 64) is None  # unknown hash is a miss, not an error


def test_reopening_reads_persisted_results(tmp_path, result_windowed):
    root = tmp_path / "proj"
    Project.open(root).put_result(result_windowed)
    reopened = Project.open(root)  # fresh handle over the same directory
    assert reopened.get_result(result_windowed.result_key) == result_windowed
