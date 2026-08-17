"""CREST water balance (crestimap.lsm) — validation.

The reference is CREST-iMAP **v1**'s own Cython routine, `cresthh/crest/crest_simp.pyx`.
`test_matches_v1_cython` is the real regression guard: it runs v1's compiled routine
side by side with this port and requires agreement to 1e-12 m. It is skipped unless
the v1 extension is importable (it needs a Python-3 Cython build of crest_simp), so
the suite stays runnable without v1 checked out; the remaining tests are
self-contained and always run.

Build the v1 reference extension with:

    cd <v1 checkout>/cresthh/crest && python setup.py build_ext --inplace

then point CRESTIMAP_V1_CREST at the directory containing the built module.
"""
import os
import sys

import pytest
import torch

from crestimap.lsm import CrestLSM, crest_core

torch.manual_seed(0)


def _v1_module():
    path = os.environ.get("CRESTIMAP_V1_CREST")
    if path and path not in sys.path:
        sys.path.insert(0, path)
    try:
        import crest_simp
        return crest_simp
    except Exception:
        return None


@pytest.mark.skipif(_v1_module() is None,
                    reason="v1 crest_simp extension not available "
                           "(set CRESTIMAP_V1_CREST to its build dir)")
def test_matches_v1_cython():
    """Bit-level agreement with the v1 CREST water balance over a wide sample."""
    crest_simp = _v1_module()
    n, dt = 2000, 3600.0
    g = torch.Generator().manual_seed(7)
    r = lambda lo, hi: (torch.rand(n, generator=g, dtype=torch.float64) * (hi - lo) + lo)
    precip_ms = torch.where(torch.rand(n, generator=g) < 0.25,
                            torch.zeros(n, dtype=torch.float64),
                            r(0.0, 60.0) / 1000.0 / 3600.0)
    WM, B, IM, Ksat = r(20, 500), r(0.05, 12.0), r(0.0, 0.95), r(0.0, 117.8)
    SM_m = r(0.0, 1.0) * WM / 1000.0

    over, Wo, inter = crest_core(precip_ms * dt * 1000.0, 0.0, SM_m * 1000.0,
                                 WM, B, IM, Ksat, dt / 3600.0)
    for i in range(n):
        sm1, ov1, if1, _ = crest_simp.model(
            float(precip_ms[i]), 0.0, 0.0, float(SM_m[i]), float(Ksat[i]),
            float(WM[i]), float(B[i]), float(IM[i]), 1.0, dt)
        assert abs(ov1 - float(over[i]) / 1000.0) < 1e-12
        assert abs(sm1 - float(Wo[i]) / 1000.0) < 1e-12
        assert abs(if1 - float(inter[i]) / 1000.0) < 1e-12


def test_mass_balance():
    """precip = overland + interflow + storage gain, to round-off."""
    n, dt = 500, 3600.0
    WM = torch.full((n,), 200.0, dtype=torch.float64)
    B = torch.full((n,), 1.0, dtype=torch.float64)
    IM = torch.zeros(n, dtype=torch.float64)
    Ksat = torch.full((n,), 10.0, dtype=torch.float64)
    SM0 = 0.4 * WM / 1000.0
    precip_ms = torch.linspace(0, 50, n, dtype=torch.float64) / 1000.0 / 3600.0

    over, Wo, inter = crest_core(precip_ms * dt * 1000.0, 0.0, SM0 * 1000.0,
                                 WM, B, IM, Ksat, dt / 3600.0)
    lhs = precip_ms * dt * 1000.0
    rhs = over + inter + (Wo - SM0 * 1000.0)
    assert torch.max(torch.abs(lhs - rhs)) < 1e-9


def test_no_runoff_without_rain_and_dry_state_is_stable():
    lsm = CrestLSM(WM=torch.full((8, 8), 150.0), B=torch.full((8, 8), 1.0),
                   IM=torch.zeros(8, 8), Ksat=torch.full((8, 8), 5.0),
                   init_saturation=0.3, dtype=torch.float64)
    sm_before = lsm.SM.clone()
    runoff = lsm.step(torch.zeros(8, 8, dtype=torch.float64), 3600.0)
    assert torch.all(runoff == 0)
    assert torch.allclose(lsm.SM, sm_before)      # no PET configured -> no depletion


def test_saturated_soil_runs_off_everything():
    """At capacity with no impervious fraction and no Ksat, all rain becomes runoff."""
    lsm = CrestLSM(WM=torch.full((4, 4), 100.0), B=torch.full((4, 4), 1.0),
                   IM=torch.zeros(4, 4), Ksat=torch.zeros(4, 4),
                   init_saturation=1.0, dtype=torch.float64)
    rate = 20.0 / 1000.0 / 3600.0                 # 20 mm/h
    runoff = lsm.step(torch.full((4, 4), rate, dtype=torch.float64), 3600.0)
    assert torch.allclose(runoff, torch.full((4, 4), rate, dtype=torch.float64),
                          rtol=1e-9)


def test_runon_absorb_is_bounded_by_storage():
    lsm = CrestLSM(WM=torch.full((4, 4), 100.0), B=torch.full((4, 4), 1.0),
                   IM=torch.zeros(4, 4), Ksat=torch.full((4, 4), 1e6),
                   init_saturation=0.5, dtype=torch.float64)
    take = lsm.runon_rate(3600.0) * 3600.0
    assert torch.all(take <= lsm.WM / 1000.0 - lsm.SM + 1e-12)
    lsm.absorb(take)
    assert torch.all(lsm.SM <= lsm.WM / 1000.0 + 1e-12)


def test_baseflow_reservoir_conserves_mass():
    """released + remaining == banked, at any dt."""
    lsm = CrestLSM(WM=torch.full((4, 4), 200.0), B=torch.full((4, 4), 1.0),
                   IM=torch.zeros(4, 4), Ksat=torch.full((4, 4), 20.0),
                   init_saturation=0.5, dtype=torch.float64,
                   baseflow={"enabled": True, "tau_hours": 12.0})
    lsm.step(torch.full((4, 4), 30.0 / 1000.0 / 3600.0, dtype=torch.float64), 3600.0)
    banked = lsm.RS.clone()
    dt = 1800.0
    released = lsm.baseflow_rate(dt) * dt
    assert torch.max(torch.abs((released + lsm.RS) - banked)) < 1e-12


def test_runs_on_cuda_if_available():
    if not torch.cuda.is_available():
        pytest.skip("no CUDA device")
    try:
        lsm = CrestLSM(WM=torch.full((32, 32), 200.0), B=torch.full((32, 32), 2.0),
                       IM=torch.zeros(32, 32), Ksat=torch.full((32, 32), 8.0),
                       init_saturation=0.5, device="cuda")
        out = lsm.step(torch.full((32, 32), 10.0 / 1000.0 / 3600.0,
                                  device="cuda"), 3600.0)
    except RuntimeError as e:
        # shared clusters commonly run the GPU in Exclusive_Process mode, so the
        # device can be legitimately held by another job — that is not a failure
        # of this code.
        if "busy or unavailable" in str(e) or "out of memory" in str(e):
            pytest.skip(f"CUDA device unavailable: {e}")
        raise
    assert out.is_cuda and torch.isfinite(out).all()
