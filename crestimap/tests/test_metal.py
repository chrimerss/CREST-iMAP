"""Apple Metal (mps) backend, on the float32 production path.

test_event and test_session also run here with CRESTIMAP_TEST_DEVICE=mps.
test_solver and test_forcing cannot: they assert float64 precision, which Metal does
not have.
"""
import dataclasses
import datetime
import json
import pathlib
import sys
import tempfile

import pytest
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from crestimap import EventConfig, SWESolver, resolve_device, run_event
from crestimap.session import EventSession

needs_mps = pytest.mark.skipif(not torch.backends.mps.is_available(),
                               reason="no Metal device")
F32 = torch.float32
RAIN = 50.0 / 1000.0 / 3600.0
QUARTER = datetime.timedelta(minutes=15)


def _bed(n=48):
    s = torch.linspace(0.0, 1.0, n, dtype=torch.float64)
    y, x = torch.meshgrid(s, s, indexing="ij")
    return 6.0 * x + 2.0 * torch.sin(9.0 * y) * torch.cos(7.0 * x)


def _setup(device, pool=2.0, **kw):
    z = _bed().to(dtype=F32, device=device)
    h = (pool - z).clamp(min=0.0)
    q = torch.zeros_like(z)
    return SWESolver(z, 30.0, 30.0, n_manning=0.05, **kw), h, q, q.clone()


def _flowing(device):
    """A wet domain with water moving everywhere, so roughness matters."""
    solver, h, _, qy = _setup(device, pool=20.0)
    solver.n = torch.tensor(0.05, dtype=F32, device=device, requires_grad=True)
    return solver, h, 0.05 * h, qy


def _integrate(device, nsteps=60):
    solver, h, qx, qy = _setup(device)
    h[:, :24] += 1.0     # a dam break, so water moves on both axes over the bumps
    rain = torch.full_like(h, RAIN)
    for _ in range(nsteps):
        h, qx, qy, _ = solver.step(h, qx, qy, dt=0.5, rain=rain)
    return h.cpu(), qx.cpu(), qy.cpu()


def _record_solver_device(monkeypatch):
    seen = []
    init = SWESolver.__init__

    def spy(self, z, *a, **kw):
        seen.append(z.device.type)
        init(self, z, *a, **kw)

    monkeypatch.setattr(SWESolver, "__init__", spy)
    return seen


@pytest.mark.parametrize("cuda, mps, expected", [(True, True, "cuda"),
                                                 (True, False, "cuda"),
                                                 (False, True, "mps"),
                                                 (False, False, "cpu")])
def test_auto_prefers_cuda_then_metal_then_cpu(monkeypatch, cuda, mps, expected):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: cuda)
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: mps)
    assert resolve_device() == expected
    assert resolve_device("cuda:1") == "cuda:1"


@needs_mps
def test_metal_matches_cpu_float32():
    a, b = _integrate("cpu"), _integrate("mps")
    # the tolerance must be well under what the physics moves, or this proves nothing
    assert a[1].abs().max() > 0.1 and a[2].abs().max() > 0.1
    for x, y in zip(a, b):
        assert torch.isfinite(y).all()
        assert (x - y).abs().max() < 1e-5


@needs_mps
def test_metal_lake_at_rest():
    solver, h, qx, qy = _setup("mps", pool=20.0)
    h0 = h.clone()
    for _ in range(20):
        h, qx, qy, _ = solver.step(h, qx, qy, dt=0.5)
    assert (h - h0).abs().max() < 1e-4
    assert max(qx.abs().max(), qy.abs().max()) < 1e-3


@needs_mps
def test_metal_dry_start_does_not_create_water():
    solver, h, qx, qy = _setup("mps", pool=-100.0)
    assert h.sum() == 0.0
    rain = torch.full_like(h, RAIN)
    t = 0.0
    while t < 600.0:
        h, qx, qy, dt = solver.step(h, qx, qy, rain=rain)
        t += dt
    supplied = RAIN * t * h.numel()
    assert h.cpu().double().sum().item() == pytest.approx(supplied, rel=1e-4)


@needs_mps
def test_metal_gradient_matches_cpu():
    grads = []
    for device in ("cpu", "mps"):
        solver, h, qx, qy = _flowing(device)
        rain = torch.full_like(h, RAIN)
        for _ in range(20):
            h, qx, qy, _ = solver.step(h, qx, qy, dt=0.5, rain=rain)
        # squared depth: total water does not depend on roughness
        (h ** 2).sum().backward()
        grads.append(solver.n.grad.item())
    assert abs(grads[0]) > 1e-3
    assert grads[1] == pytest.approx(grads[0], rel=1e-3)


@needs_mps
def test_metal_checkpointed_run_matches_plain_gradient():
    grads = []
    for every in (0, 1):
        solver, h, qx, qy = _flowing("mps")
        h = h.clone().requires_grad_()
        out = solver.run(h, qx, qy, t_end=5.0, checkpoint_every=every)
        (out[0] ** 2).sum().backward()
        assert torch.isfinite(h.grad).all()
        grads.append(solver.n.grad.item())
    assert abs(grads[0]) > 1e-3
    assert grads[1] == pytest.approx(grads[0], rel=1e-3)


@needs_mps
def test_run_event_auto_on_metal(monkeypatch):
    pytest.importorskip("rasterio")
    from test_event import N, NXC, NYC, SEC3, T0, W, _synthetic_event_dir
    seen = _record_solver_device(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        dem_path = _synthetic_event_dir(d)
        log = []
        cfg = EventConfig(
            event_id="metal", bbox=(W, N - NYC * SEC3, W + NXC * SEC3, N),
            t0=T0, t_end=T0 + QUARTER, ef5_output_dir=str(d),
            out_dir=str(d / "out"), model="crest", sim_start=T0,
            dem_path=dem_path, output_every_s=900.0, device="auto",
            progress=log.append)
        man = run_event(cfg)
        assert json.loads((d / "out" / "manifest.json").read_text())
    assert seen == ["mps"]
    assert cfg.device == "auto"                    # the caller's config is untouched
    assert any("channel pre-wet" in line for line in log)   # the float64 q grid path
    assert man["frames"]


@needs_mps
@pytest.mark.parametrize("ambient", [False, True])
def test_session_auto_on_metal(monkeypatch, ambient):
    pytest.importorskip("rasterio")
    from test_session import T0, _cfg, _synthetic_dir
    seen = _record_solver_device(monkeypatch)
    dtype = torch.get_default_dtype()
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        cfg = dataclasses.replace(_cfg(d, _synthetic_dir(d), d / "out"), sim_start=T0)
        if ambient:   # a host app's default device, see EventSession's q grid setup
            torch.set_default_dtype(F32)
            torch.set_default_device("mps")
        try:
            session = EventSession(cfg, resume=False)
            man = session.advance(str(d), str(d / "out"), T0, T0 + QUARTER,
                                  device="auto")
        finally:
            torch.set_default_device(None)
            torch.set_default_dtype(dtype)
    assert seen and set(seen) == {"mps"}
    assert man["frames"]
