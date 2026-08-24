"""P2 S2: the result serializer round-trips exactly, including inf and nesting."""

from engine.store import serialize


def test_windowed_result_round_trips(result_windowed):
    assert serialize.loads(serialize.dumps(result_windowed)) == result_windowed


def test_infinities_round_trip(result_unbounded):
    r = result_unbounded
    assert r.sow is not None and r.sow.off_min_uA == float("inf")  # precondition
    back = serialize.loads(serialize.dumps(r))
    assert back == r
    assert back.sow is not None and back.sow.off_min_uA == float("inf")


def test_inactive_result_round_trips(result_inactive):
    r = result_inactive
    assert not r.activated and r.sow is None and r.window is None
    assert serialize.loads(serialize.dumps(r)) == r


def test_tuple_and_dict_types_survive(result_windowed):
    back = serialize.loads(serialize.dumps(result_windowed))
    # per_electrode is a tuple, off-target map is a dict: decode must preserve both
    assert isinstance(back.safety_at_target.per_electrode, tuple)
    assert isinstance(back.thresholds.off_target_thresholds_uA, dict)
    assert (
        back.thresholds.off_target_thresholds_uA
        == result_windowed.thresholds.off_target_thresholds_uA
    )
