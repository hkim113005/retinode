"""Property-based tests: invariants that must hold for *all* inputs, not examples.

Hypothesis generates many cases and shrinks failures to a minimal example — it
catches whole classes of bug that hand-picked examples miss. The same technique
carries the physics invariants in later layers (linearity, 1/r decay, symmetry).
"""

from hypothesis import given
from hypothesis import strategies as st

from engine import spec

ids = st.text(min_size=1, max_size=6)
reals = st.floats(allow_nan=False, allow_infinity=False)


@given(st.dictionaries(ids, reals))
def test_from_map_roundtrips_any_weight_mapping(weights):
    cfg = spec.StimConfig.from_map(weights, waveform=spec.Waveform(phase_width_us=100.0))
    # Canonical storage: always sorted by electrode id.
    assert list(cfg.weights) == sorted(cfg.weights)
    # Lossless round-trip back to the original mapping.
    assert cfg.weight_map() == weights


@given(
    st.floats(min_value=-1e6, max_value=1e6),
    st.floats(min_value=-1e6, max_value=1e6),
    st.integers(min_value=2, max_value=50),
)
def test_linspace_spans_endpoints_monotonically(start, stop, num):
    values = spec.Sweep.linspace("p", start, stop, num).values
    assert len(values) == num
    assert values[0] == start          # first value is exactly start
    assert values[-1] == stop          # last value is exactly stop (pinned)
    if start <= stop:
        assert all(a <= b for a, b in zip(values, values[1:], strict=False))
    else:
        assert all(a >= b for a, b in zip(values, values[1:], strict=False))
