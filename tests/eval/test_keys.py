"""S7 + P2 S1: composite cache keys are deterministic and sensitive to every input."""

import numpy as np

from engine import spec
from engine.store.keys import field_key, query_points_digest, result_key

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
COND2 = spec.HomogeneousConductivity(sigma_S_per_m=2.0)
ARR = spec.ElectrodeArray(
    electrodes=(spec.Electrode(id="e", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
)
ARR2 = spec.ElectrodeArray(
    electrodes=(spec.Electrode(id="e", pos_um=(5.0, 0.0, 0.0), shape="disk", size_um=10.0),)
)
CFG = spec.StimConfig.from_map({"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0))
CFG2 = spec.StimConfig.from_map({"e": -1.0}, waveform=spec.Waveform(phase_width_us=100.0))


def _patch(soma=(0.0, 0.0, -20.0)):
    return spec.RetinalPatch(
        cells=(spec.RGC(id="t", cell_type="parasol_on", soma_um=soma),),
        target_id="t",
    )


def _off():
    from engine.eval import OffTargetSet

    return OffTargetSet()


def test_field_key_is_deterministic_and_input_sensitive():
    base = field_key(ARR, COND, "analytical")
    assert base == field_key(ARR, COND, "analytical")  # deterministic
    assert base != field_key(ARR2, COND, "analytical")  # array matters
    assert base != field_key(ARR, COND2, "analytical")  # conductivity matters
    assert base != field_key(ARR, COND, "fem")  # backend matters


def test_field_key_threads_solve_params_so_fem_meshes_do_not_collide():
    coarse = "deg=1|hw=200;d=200;he=4;hf=50"
    fine = "deg=1|hw=200;d=200;he=2;hf=50"
    base = field_key(ARR, COND, "fem_fenicsx")
    k_coarse = field_key(ARR, COND, "fem_fenicsx", solve_params=coarse)
    k_fine = field_key(ARR, COND, "fem_fenicsx", solve_params=fine)
    assert k_coarse != k_fine  # different mesh -> different key (no silent reuse)
    assert k_coarse == field_key(ARR, COND, "fem_fenicsx", solve_params=coarse)  # deterministic
    assert base != k_coarse  # adding solve_params changes the key
    # the analytical backend passes no solve_params, so its keys are unchanged
    assert field_key(ARR, COND, "analytical") == field_key(
        ARR, COND, "analytical", solve_params=None
    )


def test_field_key_includes_query_points_for_per_cell_caching():
    pts1 = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    pts2 = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    base = field_key(ARR, COND, "analytical")
    k1 = field_key(ARR, COND, "analytical", pts1)
    assert k1 != base  # adding query points changes the key
    assert k1 == field_key(ARR, COND, "analytical", pts1)  # deterministic
    assert k1 != field_key(ARR, COND, "analytical", pts2)  # placement matters
    assert base == field_key(ARR, COND, "analytical", None)  # omitting reproduces the regime key


def test_query_points_digest_is_stable_and_rounds_float_noise():
    a = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    b = np.array([[1.0 + 1e-9, 2.0, 3.0], [4.0, 5.0, 6.0]])  # sub-rounding jitter
    c = np.array([[1.001, 2.0, 3.0], [4.0, 5.0, 6.0]])
    assert query_points_digest(a) == query_points_digest(a)  # deterministic
    assert query_points_digest(a) == query_points_digest(b)  # 1e-9 rounds away
    assert query_points_digest(a) != query_points_digest(c)  # a real move does not


def test_result_key_changes_with_every_scored_input():
    from engine.eval import OffTargetSet

    def key(*, array=ARR, cond=COND, cfg=CFG, patch=None, off=None, backend="analytical", ver="1"):
        return result_key(
            array,
            cond,
            cfg,
            patch or _patch(),
            off or _off(),
            backend_name=backend,
            evaluator_version=ver,
        )

    base = key()
    assert base == key()  # deterministic
    assert base != key(array=ARR2)
    assert base != key(cond=COND2)
    assert base != key(cfg=CFG2)
    assert base != key(patch=_patch(soma=(10.0, 0.0, -20.0)))
    assert base != key(off=OffTargetSet(soma_radius_um=80.0))
    assert base != key(backend="fem")
    assert base != key(ver="2")
