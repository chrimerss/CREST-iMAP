"""Validation suite for the v2 solver.

Run:  python -m pytest crestimap/tests -q     (or run this file directly)

1. Well-balance (C-property): lake at rest over irregular bathymetry stays
   at rest to machine precision, orders 1 and 2, including dry hills.
2. Stoker dam break: second-order solution matches the analytic profile.
3. Mass conservation: closed basin + lateral inflow gains exactly the
   injected volume.
4. Gradients: d(loss)/d(Manning n) and d(loss)/d(bed scale) from autograd
   match central finite differences.
"""
import math
import sys
import pathlib

import numpy as np
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from crestimap import SWESolver, stoker_dambreak

torch.set_default_dtype(torch.float64)


def _bumpy_bed(ny, nx, amp=0.3):
    y, x = torch.meshgrid(torch.linspace(0, 1, ny), torch.linspace(0, 1, nx),
                          indexing="ij")
    return (amp * torch.sin(3 * math.pi * x) * torch.cos(2 * math.pi * y)
            + 0.2 * amp * torch.sin(9.7 * x + 5.1 * y))


def test_well_balanced_wet():
    for order in (1, 2):
        z = _bumpy_bed(24, 31)
        eta0 = 1.0
        h = torch.clamp(eta0 - z, min=0.0)
        s = SWESolver(z, dx=2.0, dy=2.0, order=order, bc="wall")
        qx = torch.zeros_like(h)
        qy = torch.zeros_like(h)
        h2, qx2, qy2 = s.run(h.clone(), qx, qy, t_end=5.0)
        umax = max(qx2.abs().max().item(), qy2.abs().max().item())
        detamax = ((h2 + z) - eta0).abs().max().item()
        assert umax < 1e-12, f"order {order}: residual momentum {umax:.3e}"
        assert detamax < 1e-12, f"order {order}: surface drift {detamax:.3e}"


def test_well_balanced_dry_hills():
    """Partially dry lake at rest: hills poke above the surface."""
    for order in (1, 2):
        z = _bumpy_bed(24, 31, amp=1.4)  # peaks above eta0
        eta0 = 1.0
        h = torch.clamp(eta0 - z, min=0.0)
        s = SWESolver(z, dx=2.0, dy=2.0, order=order, bc="wall")
        h2, qx2, qy2 = s.run(h.clone(), torch.zeros_like(h), torch.zeros_like(h),
                             t_end=5.0)
        umax = max(qx2.abs().max().item(), qy2.abs().max().item())
        assert umax < 1e-12, f"order {order}: dry-hill residual {umax:.3e}"


def test_stoker_dambreak():
    nx, ny = 800, 4
    L = 40.0
    dx = L / nx
    x = (np.arange(nx) + 0.5) * dx - L / 2
    hl, hr = 1.0, 0.2
    z = torch.zeros(ny, nx)
    h = torch.where(torch.as_tensor(x) < 0, hl, hr).expand(ny, nx).clone()
    s = SWESolver(z, dx=dx, dy=dx, order=2, bc="open", n_manning=0.0, cfl=0.4)
    t_end = 1.5
    h2, qx2, _ = s.run(h, torch.zeros_like(h), torch.zeros_like(h), t_end=t_end)
    href, uref = stoker_dambreak(x, t_end, hl, hr)
    hsim = h2[ny // 2].numpy()
    rel_l1 = np.abs(hsim - href).mean() / href.mean()
    # middle-state depth (sample well inside the plateau)
    plateau = (x > 1.0) & (x < 3.0)
    hm_err = abs(hsim[plateau].mean() - href[plateau].mean()) / href[plateau].mean()
    assert rel_l1 < 0.03, f"dam break L1 error {rel_l1:.4f}"
    assert hm_err < 0.02, f"middle state error {hm_err:.4f}"


def test_mass_conservation_with_inflow():
    z = _bumpy_bed(20, 20, amp=0.2)
    h = torch.clamp(0.5 - z, min=0.0)
    dx = dy = 5.0
    s = SWESolver(z, dx=dx, dy=dy, order=2, bc="wall")
    rate = 1e-4  # m/s lateral inflow everywhere
    rain = lambda t: torch.full_like(h, rate)
    v0 = h.sum().item() * dx * dy
    t_end = 20.0
    h2, _, _ = s.run(h, torch.zeros_like(h), torch.zeros_like(h),
                     t_end=t_end, rain_fn=rain)
    v1 = h2.sum().item() * dx * dy
    v_in = rate * t_end * dx * dy * h.numel()
    assert abs((v1 - v0) - v_in) / v_in < 1e-10, \
        f"mass error {(v1 - v0) - v_in:.3e} of {v_in:.3e}"


def _grad_loss(n_scalar, zscale, nsteps=25):
    """Fixed-dt run returning a scalar loss; used for autograd vs FD."""
    ny, nx = 12, 16
    base = _bumpy_bed(ny, nx, amp=0.15)
    z = base * zscale
    h = torch.clamp(0.8 - z, min=0.0) + 0.05
    s = SWESolver(z, dx=2.0, dy=2.0, order=2, bc="wall", n_manning=n_scalar)
    qx = torch.zeros_like(h)
    qy = torch.zeros_like(h)
    # slosh: tilt the surface so there is real dynamics + friction
    h = h + 0.05 * torch.linspace(-1, 1, nx).expand(ny, nx)
    dt = 0.05
    rain = torch.full_like(h, 2e-5)
    for _ in range(nsteps):
        h, qx, qy, _ = s.step(h, qx, qy, dt=dt, rain=rain)
    w = torch.linspace(0.5, 1.5, nx).expand(ny, nx)
    return (h * w).sum()


def test_gradients_match_fd():
    for name, val in (("manning", 0.05), ("zscale", 1.0)):
        p = torch.tensor(val, requires_grad=True)
        if name == "manning":
            loss = _grad_loss(p, torch.tensor(1.0))
        else:
            loss = _grad_loss(torch.tensor(0.05), p)
        loss.backward()
        g_auto = p.grad.item()
        d = 1e-6 if name == "manning" else 1e-6
        args = lambda v: (torch.tensor(v), torch.tensor(1.0)) if name == "manning" \
            else (torch.tensor(0.05), torch.tensor(v))
        lp = _grad_loss(*args(val + d)).item()
        lm = _grad_loss(*args(val - d)).item()
        g_fd = (lp - lm) / (2 * d)
        denom = max(abs(g_fd), 1e-8)
        rel = abs(g_auto - g_fd) / denom
        assert rel < 1e-4, f"{name}: autograd {g_auto:.6e} vs FD {g_fd:.6e} (rel {rel:.2e})"


if __name__ == "__main__":
    for fn in (test_well_balanced_wet, test_well_balanced_dry_hills,
               test_stoker_dambreak, test_mass_conservation_with_inflow,
               test_gradients_match_fd):
        fn()
        print(f"PASS  {fn.__name__}")
    print("all tests passed")
