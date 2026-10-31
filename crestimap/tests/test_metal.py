"""Apple Metal (mps) backend, on the float32 production path.

The rest of the suite also runs here with CRESTIMAP_TEST_DEVICE=mps for test_event
and test_session. test_solver and test_forcing cannot: they assert float64 precision,
which Metal does not have.
"""
import pathlib
import sys
import warnings

import pytest
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from crestimap import SWESolver, resolve_device

needs_mps = pytest.mark.skipif(not torch.backends.mps.is_available(),
                               reason="no Metal device")
F32 = torch.float32
RAIN = 50.0 / 1000.0 / 3600.0


def _bed(n=48):
    s = torch.linspace(0.0, 1.0, n, dtype=torch.float64)
    y, x = torch.meshgrid(s, s, indexing="ij")
    return 6.0 * x + 2.0 * torch.sin(9.0 * y) * torch.cos(7.0 * x)


def _setup(device, pool=2.0, **kw):
    z = _bed().to(dtype=F32, device=device)
    h = (pool - z).clamp(min=0.0)
    q = torch.zeros_like(z)
    return SWESolver(z, 30.0, 30.0, n_manning=0.05, **kw), h, q, q.clone()


def _integrate(device, nsteps=60):
    solver, h, qx, qy = _setup(device)
    rain = torch.full_like(h, RAIN)
    for _ in range(nsteps):
        h, qx, qy, _ = solver.step(h, qx, qy, dt=0.5, rain=rain)
    return h.cpu(), qx.cpu(), qy.cpu()


def test_resolve_device():
    assert resolve_device("cpu") == "cpu"
    assert resolve_device("cuda:1") == "cuda:1"
    auto = resolve_device()
    if torch.cuda.is_available():
        assert auto == "cuda"
    elif torch.backends.mps.is_available():
        assert auto == "mps"
    else:
        assert auto == "cpu"


@needs_mps
def test_metal_matches_cpu_float32():
    a, b = _integrate("cpu"), _integrate("mps")
    assert a[0].max() > 0.0
    for x, y in zip(a, b):
        assert torch.isfinite(y).all()
        assert (x - y).abs().max() < 1e-3


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
        # wet domain: a dry cell makes the gradient NaN on every device
        solver, h, qx, qy = _setup(device, pool=20.0)
        solver.n = torch.tensor(0.05, dtype=F32, device=device, requires_grad=True)
        rain = torch.full_like(h, RAIN)
        qx = 0.05 * h      # moving water, so friction matters
        for _ in range(20):
            h, qx, qy, _ = solver.step(h, qx, qy, dt=0.5, rain=rain)
        # squared depth: total water does not depend on roughness
        (h ** 2).sum().backward()
        grads.append(solver.n.grad.item())
    assert grads[0] != 0.0
    assert grads[1] == pytest.approx(grads[0], rel=0.05)


@needs_mps
def test_metal_checkpointed_run():
    solver, h, qx, qy = _setup("mps", pool=20.0)
    solver.n = torch.tensor(0.05, dtype=F32, device="mps", requires_grad=True)
    h = h.clone().requires_grad_()
    rain = torch.full_like(h, RAIN)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = solver.run(h, qx, qy, t_end=5.0, rain_fn=lambda t: rain,
                         checkpoint_every=1)
    (out[0] ** 2).sum().backward()
    assert torch.isfinite(solver.n.grad) and solver.n.grad != 0.0


@needs_mps
def test_metal_refuses_float64():
    with pytest.raises((TypeError, RuntimeError), match="float64"):
        torch.zeros(2, dtype=torch.float64, device="mps")
