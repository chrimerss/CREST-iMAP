"""Validation suite for the v2 solver.

Run:  python -m pytest crestimap/tests -q     (or run this file directly)

1. Well-balance (C-property): lake at rest over irregular bathymetry stays
   at rest to machine precision, orders 1 and 2, including dry hills.
2. Stoker dam break: second-order solution matches the analytic profile.
3. Mass conservation: closed basin + lateral inflow gains exactly the
   injected volume.
4. Gradients: d(loss)/d(Manning n) and d(loss)/d(bed scale) from autograd
   match central finite differences, on wet and on partly dry domains.
5. Water budget from a dry start: rain on dry ground creates no water at any
   dt_max, rain-aware dt, cfl cap, step_limited retries stay differentiable.
"""
import math
import os
import sys
import pathlib
import warnings

import numpy as np
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from crestimap import SWESolver, stoker_dambreak
from crestimap.solver import safe_sqrt

torch.set_default_dtype(torch.float64)
# CRESTIMAP_TEST_DEVICE=cuda runs the whole suite on the GPU (P1 gate 1)
DEVICE = os.environ.get("CRESTIMAP_TEST_DEVICE", "cpu")
if DEVICE != "cpu":
    torch.set_default_device(DEVICE)


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
    hsim = h2[ny // 2].cpu().numpy()
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
    # spatially VARYING inflow: drives real dynamics + boundary-adjacent
    # gradients, which is what exposes any wall-face mass leak
    rate = 1e-4 * (1.0 + torch.rand(20, 20))
    rain = lambda t: rate
    v0 = h.sum().item() * dx * dy
    t_end = 20.0
    h2, _, _ = s.run(h, torch.zeros_like(h), torch.zeros_like(h),
                     t_end=t_end, rain_fn=rain)
    v1 = h2.sum().item() * dx * dy
    v_in = rate.sum().item() * t_end * dx * dy
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


RAIN_50MM_H = 50e-3 / 3600.0


def _tilted_plane(n=40, dx=30.0, slope=0.01, dtype=None):
    x = torch.arange(n, dtype=dtype or torch.get_default_dtype()) * dx
    return (slope * x).expand(n, n).clone()


def _rough_bed(n=64, sigma=1.0):
    """White-noise bed: pits and spikes wet unevenly, so the rain-aware dt alone
    is not enough and the retry backstop has to act."""
    torch.manual_seed(0)
    return sigma * torch.randn(n, n)


def _dry_run_budget(s, t_end, rain_fn):
    """Run from a dry start. Returns (relative budget error, last callback t)."""
    h0 = torch.zeros_like(s.z)
    seen = []
    h, _, _ = s.run(h0, h0.clone(), h0.clone(), t_end=t_end, rain_fn=rain_fn,
                    callback=lambda t, *_: seen.append(t))
    supplied = rain_fn.total if hasattr(rain_fn, "total") else (
        rain_fn(0.0).sum().item() * t_end)
    return (h.sum().item() - supplied) / supplied, seen[-1]


def test_rain_on_dry_spot_creates_no_water():
    """One raining cell on a dry 1 m grid at dt_max=60: the old dt took the full
    60 s and clipping left 5.42x the rain supplied on the grid."""
    z = torch.zeros(16, 16)
    rain = torch.zeros(16, 16)
    rain[8, 8] = RAIN_50MM_H
    s = SWESolver(z, dx=1.0, dy=1.0, dt_max=60.0)
    h0 = torch.zeros_like(z)
    h, _, _, dt = s.step(h0, h0.clone(), h0.clone(), rain=rain)
    supplied = RAIN_50MM_H * dt
    assert dt < 60.0, "rain must limit dt on a dry grid"
    assert abs(h.sum().item() - supplied) / supplied < 1e-12, \
        f"grid holds {h.sum().item() / supplied:.4f}x the rain supplied"


def test_dry_plane_water_budget_any_dt_max():
    """Uniform rain on a dry walled plane for an hour. dt_max must not matter:
    the old dt ended 0.8% high at 60 s and 2x high at 3600 s."""
    for dt_max in (60.0, 600.0, 3600.0):
        z = _tilted_plane()
        rain = torch.full_like(z, RAIN_50MM_H)
        s = SWESolver(z, dx=30.0, dy=30.0, dt_max=dt_max)
        err, _ = _dry_run_budget(s, 3600.0, lambda t: rain)
        assert abs(err) < 1e-12, f"dt_max={dt_max}: mass error {err:.3e}"


def test_dry_plane_water_budget_float32():
    """The event and session paths run in float32, where 1e-13 is below the
    rounding of the sum: the backstop must neither spin nor raise."""
    z = _tilted_plane(dtype=torch.float32) + 100.0
    rain = torch.full_like(z, RAIN_50MM_H)
    s = SWESolver(z, dx=30.0, dy=30.0, dt_max=600.0)
    err, _ = _dry_run_budget(s, 3600.0, lambda t: rain)
    assert abs(err) < 1e-5, f"float32 mass error {err:.3e}"


def test_retries_conserve_water_and_advance_time():
    """Rough bed: retries really happen, and time advances by the dt taken, or
    the budget would come up short and the run would overshoot t_end."""
    z = _rough_bed()
    rain = torch.full_like(z, RAIN_50MM_H)
    s = SWESolver(z, dx=30.0, dy=30.0, dt_max=600.0)
    err, t_last = _dry_run_budget(s, 1800.0, lambda t: rain)
    assert abs(err) < 1e-12, f"mass error {err:.3e}"
    assert abs(t_last - 1800.0) < 1e-9
    assert s.n_retries > 0, "case no longer exercises the backstop"


def test_retries_land_on_forcing_switch():
    """A retried step must not lose the next_change landing: the rate switches
    at 600 s and each rate must act for exactly its window."""
    z = _rough_bed()
    wet = torch.full_like(z, RAIN_50MM_H)
    light = 0.1 * wet

    def rain_fn(t):
        return wet if t < 600.0 - 1e-9 else light
    rain_fn.next_change = lambda t: 600.0 - t if t < 600.0 - 1e-9 else float("inf")
    rain_fn.total = wet.sum().item() * 600.0 + light.sum().item() * 300.0
    s = SWESolver(z, dx=30.0, dy=30.0, dt_max=600.0)
    err, _ = _dry_run_budget(s, 900.0, rain_fn)
    assert abs(err) < 1e-12, f"mass error {err:.3e}"
    assert s.n_retries > 0, "case no longer exercises the backstop"


def test_compute_dt_solves_rain_limit():
    z = _rough_bed(16, 0.1)
    h = torch.clamp(0.5 - z, min=0.0)
    qx = 0.3 * h
    qy = -0.1 * h
    rain = torch.full_like(z, RAIN_50MM_H)
    rain[3, 4] = 40.0 * RAIN_50MM_H
    s = SWESolver(z, dx=10.0, dy=5.0, dt_max=1e6)
    plain = s.compute_dt(h, qx, qy)
    u = (qx / h).abs()
    v = (qy / h).abs()
    c = torch.sqrt(s.g * h)
    speed = max(((u + c) / 10.0).max().item(), ((v + c) / 5.0).max().item())
    assert abs(plain - s.cfl / speed) / plain < 1e-6
    # the root of dt (s + k sqrt(dt)) = cfl, and tighter than the plain limit
    k = math.sqrt(s.g * 40.0 * RAIN_50MM_H) / 5.0
    dt = s.compute_dt(h, qx, qy, rain)
    speed = s.cfl / plain
    assert dt < plain
    assert abs(dt * (speed + k * math.sqrt(dt)) - s.cfl) < 1e-12
    # a dry grid has only the rain term; dt_max still caps; no rain = no limit
    dry = torch.zeros_like(z)
    dt = s.compute_dt(dry, dry, dry, rain)
    assert abs(k * dt ** 1.5 - s.cfl) < 1e-12
    assert SWESolver(z, 10.0, 5.0, dt_max=3.0).compute_dt(dry, dry, dry, rain) == 3.0
    assert s.compute_dt(dry, dry, dry) == 1e6
    assert s.compute_dt(dry, dry, dry, torch.zeros_like(z)) == 1e6


def test_cfl_capped():
    z = torch.zeros(8, 8)
    h = torch.full_like(z, 1.0)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        unsafe = SWESolver(z, dx=1.0, dy=1.0, cfl=0.9)
    assert any("cfl" in str(w.message) for w in caught), "no warning for capped cfl"
    assert unsafe.cfl == 0.5
    at_cap = SWESolver(z, dx=1.0, dy=1.0, cfl=0.5)
    assert unsafe.compute_dt(h, 0 * h, 0 * h) == at_cap.compute_dt(h, 0 * h, 0 * h)
    for bad in (0.0, -0.1):
        try:
            SWESolver(z, dx=1.0, dy=1.0, cfl=bad)
        except AssertionError:
            continue
        raise AssertionError(f"cfl={bad} accepted")


def test_explicit_dt_taken_exactly():
    """Guard: fixed-dt callers (calibration, the C-property probe) get the dt
    they asked for, however much it clips — no retry, no rain limit."""
    z = torch.zeros(16, 16)
    rain = torch.zeros(16, 16)
    rain[8, 8] = RAIN_50MM_H
    s = SWESolver(z, dx=1.0, dy=1.0, dt_max=60.0)
    h0 = torch.zeros_like(z)
    h, _, _, dt = s.step(h0, h0.clone(), h0.clone(), dt=60.0, rain=rain)
    assert dt == 60.0
    assert h.sum().item() > 2.0 * RAIN_50MM_H * 60.0, "explicit dt was not honored"
    assert s.n_retries == 0


def test_clip_measures_the_water_created():
    """clip = 0.5 clip_predictor + clip_corrector is exactly what the grid gains
    beyond the rain, with both stages clipping, and stays off the graph."""
    z = torch.zeros(16, 16)
    h = torch.zeros_like(z)
    h[:, :8] = 1.0
    h.requires_grad_(True)
    rain = torch.full_like(z, RAIN_50MM_H)
    s = SWESolver(z, dx=1.0, dy=1.0)
    q = torch.zeros_like(z)
    hn, _, _, clip = s._try_step(h, q, q, 2.0, rain)
    created = hn.sum().item() - h.sum().item() - rain.sum().item() * 2.0
    assert not clip.requires_grad
    assert clip.item() > 0.0, "case no longer clips"
    assert abs(created - clip.item()) < 1e-11 * clip.item()


def test_run_takes_the_rain_limited_dt():
    """On a flat dry grid uniform rain never clips, so the backstop stays out of
    it and run's first step shows the dt it asked for."""
    z = torch.zeros(8, 8)
    rain = torch.full_like(z, RAIN_50MM_H)
    s = SWESolver(z, dx=30.0, dy=30.0, dt_max=3600.0)
    h0 = torch.zeros_like(z)
    expected = s.compute_dt(h0, h0, h0, rain)
    assert expected < 3600.0
    seen = []
    s.run(h0, h0.clone(), h0.clone(), t_end=3.0 * expected, rain_fn=lambda t: rain,
          callback=lambda t, *_: seen.append(t))
    assert s.n_retries == 0
    assert seen[0] == expected


def test_step_limited_raises_when_it_cannot_recover():
    """A NaN state or a sink on dry ground cannot be helped by a smaller dt:
    stop with an error instead of spinning or silently creating water."""
    z = torch.zeros(8, 8)
    h = torch.ones_like(z)
    h[2, 2] = float("nan")
    s = SWESolver(z, dx=1.0, dy=1.0)
    sink = torch.full_like(z, -1e-6)
    for state, rain in (((h, 0 * z, 0 * z), None), ((0 * z, 0 * z, 0 * z), sink)):
        try:
            s.step(*state, rain=rain)
        except RuntimeError as e:
            assert "halving" in str(e)
            continue
        raise AssertionError("step_limited accepted an unrecoverable state")


def _thin_film_step(n_manning, dt_limit=None, dt=None):
    """Thin wet film on a rough bed, with a dt_limit far above CFL so the first
    attempts clip."""
    z = _rough_bed(16, 0.02)
    s = SWESolver(z, dx=5.0, dy=5.0, n_manning=n_manning)
    h = 0.02 + 0.01 * torch.linspace(0, 1, 16).expand(16, 16)
    qx = 0.002 * torch.ones_like(h)
    qy = torch.zeros_like(h)
    rain = torch.full_like(h, 1e-4)
    if dt is None:
        hn, qxn, _, dt = s.step_limited(h, qx, qy, dt_limit, rain)
    else:
        hn, qxn, _, dt = s.step(h, qx, qy, dt=dt, rain=rain)
    w = torch.linspace(0.5, 1.5, 16).expand(16, 16)
    return ((hn ** 2 + qxn ** 2) * w).sum(), dt, s   # friction only reaches q in one step


def test_retried_step_is_differentiable():
    """The accepted attempt of a retried step differentiates exactly like a
    fixed-dt step at that dt, and matches finite differences at frozen dt."""
    n = torch.tensor(0.05, requires_grad=True)
    loss, dt_used, s = _thin_film_step(n, dt_limit=64.0)
    assert s.n_retries > 0, "case no longer exercises the backstop"
    loss.backward()
    g_retry = n.grad.item()
    assert math.isfinite(g_retry) and g_retry != 0.0

    n2 = torch.tensor(0.05, requires_grad=True)
    loss2, _, _ = _thin_film_step(n2, dt=dt_used)
    loss2.backward()
    assert g_retry == n2.grad.item()

    d = 1e-6
    lp = _thin_film_step(torch.tensor(0.05 + d), dt=dt_used)[0].item()
    lm = _thin_film_step(torch.tensor(0.05 - d), dt=dt_used)[0].item()
    g_fd = (lp - lm) / (2 * d)
    assert abs(g_retry - g_fd) / abs(g_fd) < 1e-4, f"autograd {g_retry:.6e} vs FD {g_fd:.6e}"


def test_checkpointed_run_matches_plain_gradient():
    """Replaying a checkpoint during backward must retake that step's own dt
    and rain, not the last ones the run loop saw."""
    z = _rough_bed(16, 0.05)
    h0 = 0.5 + 0.1 * torch.linspace(-1, 1, 16).expand(16, 16)
    grads = []
    for every in (0, 1):
        n = torch.tensor(0.05, requires_grad=True)
        s = SWESolver(z, dx=30.0, dy=30.0, n_manning=n)
        h = h0.clone().requires_grad_(True)
        rain_fn = lambda t: torch.full_like(z, 1e-4 * (1.0 + t / 60.0))
        hn, _, _ = s.run(h, torch.zeros_like(h), torch.zeros_like(h), t_end=60.0,
                         rain_fn=rain_fn, checkpoint_every=every)
        ((hn - 0.5) ** 2).sum().backward()
        grads.append(n.grad.item())
    assert abs(grads[0] - grads[1]) <= 1e-12 * abs(grads[0]), f"{grads}"


def _partly_dry_case(name, ny=10, nx=14):
    """(bed, h0, rain) that leaves some cells dry at the end of the run."""
    y, x = torch.meshgrid(torch.linspace(0, 1, ny), torch.linspace(0, 1, nx),
                          indexing="ij")
    z = _bumpy_bed(ny, nx, amp=0.3) + 0.5 * x
    rain = torch.zeros_like(z)
    if name == "pond":        # moving pond below a dry slope, some rain on the water
        # Curved along both axes: a surface flat along one sits on a minmod kink,
        # wet or dry, where FD stops converging to any one derivative.
        eta = 0.25 + 0.1 * (1.0 - 2.0 * x) + 0.03 * torch.sin(2.3 * x + 4.1 * y) * torch.cos(3.7 * y)
        h = torch.clamp(eta - z, min=0.0)
        rain[:3, :4] = 1e-3
    elif name == "dam break":  # onto a dry bed
        h = torch.zeros_like(z)
        h[:, :5] = 0.5 + 0.03 * torch.arange(ny)[:, None]
    else:                      # dry start, rain on one patch
        h = torch.zeros_like(z)
        rain[3:6, 4:8] = 5e-2
    return z, h, rain


def _partly_dry_loss(z, h, rain, n, order, nsteps=20, dt=0.02):
    s = SWESolver(z, dx=1.0, dy=1.0, n_manning=n, order=order)
    qx = torch.zeros_like(h)
    qy = torch.zeros_like(h)
    for _ in range(nsteps):
        h, qx, qy, _ = s.step(h, qx, qy, dt=dt, rain=rain)
    w = torch.linspace(0.5, 1.5, h.shape[1]).expand_as(h)
    return ((h ** 2 + qx ** 2 + qy ** 2) * w).sum(), h


def test_gradients_match_fd_partly_dry():
    """Autograd vs finite differences at frozen dt, with dry cells in the domain,
    along random directions over the cells that end up dry and those that end up
    wet, so the larger gradients of wet cells cannot hide errors at dry ones."""
    torch.manual_seed(0)
    d = 1e-6
    for case in ("pond", "dam break", "rain patch"):
        z0, h0, rain = _partly_dry_case(case)
        n0 = 0.05 * (1.0 + 0.2 * torch.rand(z0.shape))
        for order in (1, 2):
            n = n0.clone().requires_grad_(True)
            z = z0.clone().requires_grad_(True)
            loss, hn = _partly_dry_loss(z, h0, rain, n, order)
            dry = hn.detach() == 0.0
            assert dry.any() and not dry.all(), f"{case}: no longer partly dry"
            loss.backward()
            assert n.grad.abs().max() > 0.0 and z.grad.abs().max() > 0.0
            for param, grad in (("n", n.grad), ("z", z.grad)):
                for cells, mask in (("wet", ~dry), ("dry", dry)):
                    v = torch.randn(z0.shape) * mask
                    dn, dz = (d * v, 0.0) if param == "n" else (0.0, d * v)
                    lp = _partly_dry_loss(z0 + dz, h0, rain, n0 + dn, order)[0].item()
                    lm = _partly_dry_loss(z0 - dz, h0, rain, n0 - dn, order)[0].item()
                    g_fd = (lp - lm) / (2 * d)
                    g_auto = (grad * v).sum().item()
                    assert math.isfinite(g_auto), f"{case} order {order} d{param}: NaN"
                    # 1e-15 |loss| / d is the rounding noise of the difference. Where
                    # +d and -d take the same limiter branches they agree to 1e-8;
                    # a pair straddling a minmod tie can differ by a few 1e-4.
                    tol = 1e-3 * (grad * v).abs().sum().item() + 1e-15 * abs(lp) / d
                    assert abs(g_auto - g_fd) <= tol, \
                        (f"{case} order {order} d{param} over {cells} cells: "
                         f"autograd {g_auto:.6e} vs FD {g_fd:.6e}, tol {tol:.1e}")


def test_gradients_finite_from_dry_start():
    """Still and dry cells have no velocity, so friction's sqrt(u^2 + v^2) sits at 0
    and 0/0 would poison every gradient behind it: rain on a flat dry grid gave 100%
    NaN. There is no flow here, so n has no effect at all. On an exactly flat bed
    z is at a kink, so this checks z for being finite but not against FD."""
    z = torch.zeros(16, 16, requires_grad=True)
    n = torch.tensor(0.05, requires_grad=True)
    s = SWESolver(z, dx=2.0, dy=2.0, n_manning=n)
    h = torch.zeros(16, 16)
    qx = qy = torch.zeros_like(h)
    rain = torch.full_like(h, 1e-4)
    with torch.autograd.detect_anomaly(check_nan=True):
        for _ in range(20):
            h, qx, qy, _ = s.step(h, qx, qy, dt=0.05, rain=rain)
        (h ** 2).sum().backward()
    assert n.grad.item() == 0.0
    assert z.grad.isfinite().all()


def test_gradients_finite_lake_at_rest_with_dry_hills():
    z = _bumpy_bed(24, 31, amp=1.4).requires_grad_(True)
    n = torch.tensor(0.05, requires_grad=True)
    s = SWESolver(z, dx=2.0, dy=2.0, n_manning=n)
    h = torch.clamp(1.0 - z.detach(), min=0.0)
    qx = qy = torch.zeros_like(h)
    for _ in range(20):
        h, qx, qy, _ = s.step(h, qx, qy, dt=0.05)
    assert (h == 0.0).any()
    (h ** 2).sum().backward()
    assert n.grad.isfinite() and z.grad.isfinite().all()


def test_adaptive_run_differentiates_from_dry_start():
    """The real calibration path: rough dry ground, rain, retries and checkpoints."""
    z = _rough_bed(16, 0.2)
    grads = []
    for every in (0, 1):
        n = torch.tensor(0.05, requires_grad=True)
        s = SWESolver(z, dx=30.0, dy=30.0, n_manning=n, dt_max=600.0)
        h0 = torch.zeros_like(z).requires_grad_(every > 0)   # checkpoint needs it
        rain = torch.full_like(z, RAIN_50MM_H)
        hn, _, _ = s.run(h0, torch.zeros_like(z), torch.zeros_like(z), t_end=600.0,
                         rain_fn=lambda t: rain, checkpoint_every=every)
        (hn ** 2).sum().backward()
        assert s.n_retries > 0, "case no longer exercises the backstop"
        assert h0.grad is None or h0.grad.isfinite().all()
        grads.append(n.grad.item())
    assert math.isfinite(grads[0]) and grads[0] != 0.0
    assert abs(grads[0] - grads[1]) <= 1e-12 * abs(grads[0]), f"{grads}"


def test_safe_sqrt():
    """torch.sqrt's values bit for bit, its gradient except at 0, where it is 0."""
    x = torch.tensor([0.0, -0.0, 1e-300, 2.0, float("inf"), -1.0, float("nan")])
    for y in (x, x.clone().requires_grad_(True)):
        assert safe_sqrt(y).detach().numpy().tobytes() == torch.sqrt(x).numpy().tobytes()
    t = torch.tensor([0.0, 1e-300, 2.0], requires_grad=True)
    safe_sqrt(t).sum().backward()
    assert t.grad[0] == 0.0
    assert t.grad[1:].tolist() == [0.5 / math.sqrt(v) for v in (1e-300, 2.0)]


if __name__ == "__main__":
    for fn in (test_well_balanced_wet, test_well_balanced_dry_hills,
               test_stoker_dambreak, test_mass_conservation_with_inflow,
               test_gradients_match_fd, test_rain_on_dry_spot_creates_no_water,
               test_dry_plane_water_budget_any_dt_max,
               test_dry_plane_water_budget_float32,
               test_retries_conserve_water_and_advance_time,
               test_retries_land_on_forcing_switch,
               test_compute_dt_solves_rain_limit, test_cfl_capped,
               test_explicit_dt_taken_exactly, test_clip_measures_the_water_created,
               test_run_takes_the_rain_limited_dt,
               test_step_limited_raises_when_it_cannot_recover,
               test_retried_step_is_differentiable,
               test_checkpointed_run_matches_plain_gradient,
               test_gradients_match_fd_partly_dry,
               test_gradients_finite_from_dry_start,
               test_gradients_finite_lake_at_rest_with_dry_hills,
               test_adaptive_run_differentiates_from_dry_start, test_safe_sqrt):
        fn()
        print(f"PASS  {fn.__name__}")
    print("all tests passed")
