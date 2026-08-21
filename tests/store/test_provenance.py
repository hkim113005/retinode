"""P2 S3: the provenance log records every run and replays the keys it captured."""

from engine.eval import OffTargetSet
from engine.spec.hashing import spec_hash
from engine.store.project import Project
from engine.store.provenance import ProvenanceLog, RunRecord, make_run_record

from .conftest import ARR, COND


def _record(result, ctx):
    return make_run_record(
        result,
        array=ctx["array"],
        conductivity=ctx["conductivity"],
        off_target_set=ctx["off_target_set"],
        backend_name="analytical",
    )


# --- the record replays the keys it claims to describe -----------------------


def test_record_replays_field_and_result_keys(result_windowed, windowed_context):
    rec = _record(result_windowed, windowed_context)
    assert rec.replay_field_key() == result_windowed.field_key
    assert rec.replay_result_key() == result_windowed.result_key


def test_inline_off_target_set_hashes_to_the_recorded_hash(result_windowed, windowed_context):
    rec = _record(result_windowed, windowed_context)
    # the inline value is faithful: rebuilt, it hashes to the key's offtarget term
    assert spec_hash(OffTargetSet(**rec.off_target_set)) == rec.offtarget_hash


def test_record_captures_the_run_environment(result_windowed, windowed_context):
    rec = _record(result_windowed, windowed_context)
    assert set(rec.software) >= {"python", "numpy", "retinode"}
    assert rec.git_commit is None or isinstance(rec.git_commit, str)
    assert rec.timestamp.endswith("+00:00")  # ISO 8601, UTC


# --- the log is append-only and JSONL-round-trips ----------------------------


def test_log_round_trips_and_is_append_only(tmp_path, result_windowed, windowed_context):
    log = ProvenanceLog(tmp_path / "provenance.log")
    assert log.records() == [] and len(log) == 0
    rec = _record(result_windowed, windowed_context)
    log.append(rec)
    log.append(rec)  # a re-run appends again — history is not mutated
    records = log.records()
    assert len(records) == 2
    assert records[0] == rec  # exact JSONL round-trip
    assert log.find(result_windowed.result_key) == rec
    assert log.find("no_such_key") is None


# --- Project.record_run ties result + specs + provenance together ------------


def test_record_run_persists_result_specs_and_provenance(
    tmp_path, result_windowed, windowed_context
):
    p = Project.open(tmp_path / "proj")
    rec = p.record_run(result_windowed, **windowed_context)

    # the result is stored...
    assert p.get_result(result_windowed.result_key) == result_windowed
    # ...its spec values are retrievable by the hashes in the record...
    assert p.get_spec(rec.array_hash) == windowed_context["array"]
    assert p.get_spec(rec.config_hash) == windowed_context["config"]
    assert p.get_spec(rec.patch_hash) == windowed_context["patch"]
    assert p.get_spec(rec.conductivity_hash) == windowed_context["conductivity"]
    # ...and every stored result has a matching provenance record that replays.
    found = p.provenance.find(result_windowed.result_key)
    assert found is not None
    assert found.replay_result_key() == result_windowed.result_key


def test_record_run_persists_across_reopen(tmp_path, result_windowed, windowed_context):
    root = tmp_path / "proj"
    Project.open(root).record_run(result_windowed, **windowed_context)
    reopened = Project.open(root)
    assert reopened.get_result(result_windowed.result_key) == result_windowed
    assert reopened.provenance.find(result_windowed.result_key) is not None
    assert reopened.provenance.find("never_recorded_key") is None


def test_a_fem_record_replays_its_own_field_key():
    """``field_key`` appends ``solve_params`` whenever it is not None, and ``evaluate``
    always passes it — a non-None mesh/degree string on any FEM backend. It was not
    recorded at all, so a FEM record could never reproduce the key it claims to
    describe, and two runs at different mesh resolutions logged identical provenance
    lines. The existing coverage used backend_name="analytical", where it is None."""
    from engine.store.keys import field_key

    solve_params = "deg=2|hw=65;d=60;he=2;hf=16.25"
    fkey = field_key(ARR, COND, "fem_fenicsx", solve_params=solve_params)
    fields = dict(
        result_key="r",
        field_key=fkey,
        array_hash=spec_hash(ARR),
        conductivity_hash=spec_hash(COND),
        config_hash="c",
        patch_hash="p",
        offtarget_hash="o",
        off_target_set={},
        evaluator_version="2",
        backend_name="fem_fenicsx",
        software={},
        git_commit=None,
        seeds={},
        timestamp="t",
    )
    assert RunRecord(**fields, solve_params=solve_params).replay_field_key() == fkey
    # and the un-recorded case is exactly the bug: it cannot replay
    assert RunRecord(**fields).replay_field_key() != fkey
