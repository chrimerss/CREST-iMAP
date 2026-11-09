"""Differentiable well-balanced finite-volume shallow-water solver.

CREST-iMAP v2 hydrodynamic core.

Scheme
------
- Regular raster grid (DEM-aligned), cell-centered states (h, hu, hv).
- Hydrostatic reconstruction of Audusse et al. (2004, SIAM J. Sci. Comput.):
  well-balanced (exact lake-at-rest / C-property) and positivity-preserving.
- HLL numerical flux, first order or second order (MUSCL, minmod limiter,
  reconstruction in (h, eta=h+z, u, v) so the C-property is preserved at
  second order per Audusse et al. Sec. 4).
- SSP-RK2 (Heun) time stepping, adaptive rain-aware CFL timestep with a
  clip-measuring retry (both detached from the autograd graph so gradients
  stay well defined).
- Point-implicit Manning friction (closed form, differentiable).
- Desingularized velocities u = sqrt(2) h q / sqrt(h^4 + max(h,eps)^4)
  (Kurganov & Petrova 2007) so wet/dry fronts do not blow up, and safe_sqrt for
  wave and flow speeds so dry and still cells do not produce NaN gradients.
- Lateral inflow source term `rain` (m/s): rainfall excess or, in the
  CREST-AI coupling, EF5/CREST surface + subsurface runoff grids.

Everything is expressed as torch tensor ops, so the entire simulation is
differentiable end to end w.r.t. Manning n, bed elevation z, initial
conditions, and forcing.
"""
from __future__ import annotations

import warnings

import torch

G_DEFAULT = 9.80665

# Largest usable CFL. compute_dt limits each direction separately (max(sx, sy))
# while the x and y fluxes apply together, so above this a cell can drain through
# both axes in one step and the scheme leaves its stable range.
MAX_CFL = 0.5
# An adaptive step whose clipped negative depth adds more than this fraction of
# the water on the grid is retried with a smaller dt. Fluxes conserve water
# exactly, so clipping is the only way a step can create any: this bounds the
# mass error directly rather than guarding stability by heuristic.
CLIP_TOL = 1e-13
MAX_DT_HALVINGS = 30   # retries before step_limited gives up (dt_limit * 2^-30)


def resolve_device(device: str = "auto") -> str:
    """"auto" picks cuda, then Apple Metal (mps), then cpu; anything else passes
    through. Metal has no float64, so run it in float32 as run_event and
    EventSession do."""
    if device != "auto":
        return device
    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"


def desing_velocity(h: torch.Tensor, q: torch.Tensor, eps: float) -> torch.Tensor:
    """Desingularized velocity u = sqrt(2) h q / sqrt(h^4 + max(h,eps)^4)."""
    h4 = h ** 4
    e4 = torch.clamp(h, min=eps) ** 4
    return (2.0 ** 0.5) * h * q / torch.sqrt(h4 + e4)


def safe_sqrt(x: torch.Tensor) -> torch.Tensor:
    """torch.sqrt with zero gradient at x = 0, where backward's 0/0 would give NaN.

    Forward values are torch.sqrt's bit for bit. Zero is the right slope here:
    every use is a speed that a depth or momentum multiplies, so the product's
    derivative at x = 0 is finite and its sqrt term vanishes.
    """
    if not x.requires_grad:   # forward-only runs skip the two wheres
        return torch.sqrt(x)
    zero = x == 0
    return torch.where(zero, x.detach(), torch.sqrt(torch.where(zero, torch.ones_like(x), x)))


def minmod(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    return 0.5 * (torch.sign(a) + torch.sign(b)) * torch.minimum(a.abs(), b.abs())


def _cfl_dt(cfl: float, s: float, k: float) -> float:
    """Solve dt (s + k sqrt(dt)) = cfl for dt, by Newton in x = sqrt(dt).

    x^2 (s + k x) is convex and increasing in x, so starting from an upper
    bound the iteration descends to the root. Returns inf if nothing limits dt.
    """
    if k <= 0.0:
        return float("inf") if s < 1e-12 else cfl / s
    x = (cfl / k) ** (1.0 / 3.0)
    if s >= 1e-12:
        x = min(x, (cfl / s) ** 0.5)
    for _ in range(8):
        x -= (x * x * (s + k * x) - cfl) / (x * (2.0 * s + 3.0 * k * x))
    return x * x


class SWESolver:
    """Well-balanced HLL solver on a regular grid.

    Parameters
    ----------
    z : (ny, nx) tensor — bed elevation [m]. May require grad.
    dx, dy : cell size [m].
    n_manning : scalar or (ny, nx) tensor — Manning roughness. May require grad.
    order : 1 (robust, diffusive) or 2 (MUSCL/minmod, default).
    bc : 'wall' (reflective) or 'open' (zero-gradient outflow).
    eps : wet/dry desingularization depth [m].
    """

    def __init__(self, z, dx, dy, n_manning=0.03, g=G_DEFAULT, eps=1e-6,
                 cfl=0.45, order=2, bc="wall", dt_max=60.0):
        self.z = z if torch.is_tensor(z) else torch.as_tensor(z, dtype=torch.get_default_dtype())
        self.dtype = self.z.dtype
        self.device = self.z.device
        self.dx = float(dx)
        self.dy = float(dy)
        self.n = n_manning if torch.is_tensor(n_manning) else torch.as_tensor(
            n_manning, dtype=self.dtype, device=self.device)
        self.g = g
        self.eps = eps
        assert cfl > 0.0
        if cfl > MAX_CFL:
            warnings.warn(f"cfl={cfl} is unsafe; capped at {MAX_CFL}", stacklevel=2)
        self.cfl = min(cfl, MAX_CFL)
        self.n_retries = 0   # adaptive steps redone at a smaller dt, for cost reports
        assert order in (1, 2)
        self.order = order
        assert bc in ("wall", "open")
        self.bc = bc
        self.dt_max = dt_max

    # ------------------------------------------------------------------ #
    # boundary handling
    # ------------------------------------------------------------------ #
    @staticmethod
    def _sympad(t, axis, sign=1.0):
        """Two-ring symmetric (mirror-about-wall) padding along axis:
        [b, a | a, b, ..., y, z | z, y], optionally sign-flipped (normal
        momentum at a wall). Exact mirror symmetry makes the reconstructed
        states at wall faces symmetric, so the wall mass flux is exactly
        zero even with MUSCL slopes."""
        if axis == 1:
            left = sign * torch.flip(t[:, :2], dims=(1,))
            right = sign * torch.flip(t[:, -2:], dims=(1,))
            return torch.cat([left, t, right], dim=1)
        left = sign * torch.flip(t[:2, :], dims=(0,))
        right = sign * torch.flip(t[-2:, :], dims=(0,))
        return torch.cat([left, t, right], dim=0)

    @staticmethod
    def _reppad(t, axis):
        """Two-ring replicate (zero-gradient) padding along axis."""
        if axis == 1:
            return torch.cat([t[:, :1], t[:, :1], t, t[:, -1:], t[:, -1:]], dim=1)
        return torch.cat([t[:1, :], t[:1, :], t, t[-1:, :], t[-1:, :]], dim=0)

    def _pad(self, h, qx, qy):
        """Two ghost rings. wall: mirror h/z and tangential momentum,
        anti-mirror normal momentum; open: replicate (zero-gradient)."""
        if self.bc == "wall":
            pad_x = lambda t, s=1.0: self._sympad(t, 1, s)
            pad_y = lambda t, s=1.0: self._sympad(t, 0, s)
        else:
            pad_x = lambda t, s=1.0: self._reppad(t, 1)
            pad_y = lambda t, s=1.0: self._reppad(t, 0)
        hp = pad_y(pad_x(h))
        zp = pad_y(pad_x(self.z))
        qxp = pad_y(pad_x(qx, -1.0))          # normal to x-walls -> flip there
        qyp = pad_y(pad_x(qy), -1.0)          # normal to y-walls -> flip there
        return hp, qxp, qyp, zp

    # ------------------------------------------------------------------ #
    # MUSCL side values
    # ------------------------------------------------------------------ #
    @staticmethod
    def _sides(f, axis, order):
        """Side values of f inside each slope-cell along `axis`.

        Input is the 2-ring padded array; slopes (minmod) are computed for
        every cell that has both neighbors, i.e. the interior plus one ghost
        ring — with mirror padding the ghost slopes are exact mirrors of the
        interior ones, which keeps wall faces perfectly symmetric.
        Returns arrays trimmed to interior+1 ring along `axis` (full extent
        in the cross direction)."""
        if axis == 1:
            fc = f[:, 1:-1]
            if order == 1:
                return fc, fc
            s = minmod(f[:, 1:-1] - f[:, :-2], f[:, 2:] - f[:, 1:-1])
        else:
            fc = f[1:-1, :]
            if order == 1:
                return fc, fc
            s = minmod(f[1:-1, :] - f[:-2, :], f[2:, :] - f[1:-1, :])
        return fc - 0.5 * s, fc + 0.5 * s

    # ------------------------------------------------------------------ #
    # directional flux divergence with hydrostatic reconstruction
    # ------------------------------------------------------------------ #
    def _flux_div(self, hp, up, vp, zp, axis):
        """Flux divergence + bed source along `axis` for interior cells.

        Returns (div_h, div_qx, div_qy) shaped (ny, nx): contribution to
        dU/dt (already negated, source included).
        """
        g = self.g
        d = self.dx if axis == 1 else self.dy
        eta = hp + zp

        hL, hR = self._sides(hp, axis, self.order)
        eL, eR = self._sides(eta, axis, self.order)
        uL, uR = self._sides(up, axis, self.order)
        vL, vR = self._sides(vp, axis, self.order)
        hL = torch.clamp(hL, min=0.0)
        hR = torch.clamp(hR, min=0.0)
        zL = eL - hL
        zR = eR - hR

        if axis == 1:
            # face k lies between padded columns k and k+1
            hm, zm, um, vm = hR[:, :-1], zR[:, :-1], uR[:, :-1], vR[:, :-1]
            hpl, zpl, upl, vpl = hL[:, 1:], zL[:, 1:], uL[:, 1:], vL[:, 1:]
        else:
            hm, zm, um, vm = hR[:-1, :], zR[:-1, :], uR[:-1, :], vR[:-1, :]
            hpl, zpl, upl, vpl = hL[1:, :], zL[1:, :], uL[1:, :], vL[1:, :]

        # hydrostatic reconstruction (Audusse et al. 2004)
        zf = torch.maximum(zm, zpl)
        hms = torch.clamp(hm + zm - zf, min=0.0)
        hps = torch.clamp(hpl + zpl - zf, min=0.0)

        # normal/tangential velocities
        if axis == 1:
            unm, utm, unp, utp = um, vm, upl, vpl
        else:
            unm, utm, unp, utp = vm, um, vpl, upl

        cm = safe_sqrt(g * hms)
        cp = safe_sqrt(g * hps)
        sL = torch.clamp(torch.minimum(unm - cm, unp - cp), max=0.0)
        sR = torch.clamp(torch.maximum(unm + cm, unp + cp), min=0.0)

        # physical fluxes of the reconstructed states (normal direction)
        qnm = hms * unm
        qnp = hps * unp
        Fm = (qnm, qnm * unm + 0.5 * g * hms ** 2, qnm * utm)
        Fp = (qnp, qnp * unp + 0.5 * g * hps ** 2, qnp * utp)
        Um = (hms, qnm, hms * utm)
        Up = (hps, qnp, hps * utp)

        den = sR - sL
        tiny = torch.finfo(self.dtype).tiny * 1e10
        den = torch.where(den > tiny, den, torch.full_like(den, 1.0))
        both_zero = (sR - sL) <= tiny
        flux = []
        for k in range(3):
            f = (sR * Fm[k] - sL * Fp[k] + sL * sR * (Up[k] - Um[k])) / den
            flux.append(torch.where(both_zero, torch.zeros_like(f), f))

        # Audusse per-side pressure corrections (normal momentum only)
        corr_m = 0.5 * g * (hm ** 2 - hms ** 2)
        corr_p = 0.5 * g * (hpl ** 2 - hps ** 2)
        fn_m = flux[1] + corr_m   # face flux seen by the minus-side cell
        fn_p = flux[1] + corr_p   # face flux seen by the plus-side cell

        # centered bed-slope source inside each cell: -g*hbar*dz (2nd order)
        hbar = 0.5 * (hL + hR)
        if axis == 1:
            src = -g * hbar * (zR - zL) / d
            div_h = (flux[0][:, 1:] - flux[0][:, :-1]) / d
            div_qn = (fn_m[:, 1:] - fn_p[:, :-1]) / d
            div_qt = (flux[2][:, 1:] - flux[2][:, :-1]) / d
            src_c = src[:, 1:-1]
            sl = lambda t: t[2:-2, :]      # cross direction: drop both ghost rings
            div_h, div_qn, div_qt, src_c = map(sl, (div_h, div_qn, div_qt, src_c))
        else:
            src = -g * hbar * (zR - zL) / d
            div_h = (flux[0][1:, :] - flux[0][:-1, :]) / d
            div_qn = (fn_m[1:, :] - fn_p[:-1, :]) / d
            div_qt = (flux[2][1:, :] - flux[2][:-1, :]) / d
            src_c = src[1:-1, :]
            sl = lambda t: t[:, 2:-2]
            div_h, div_qn, div_qt, src_c = map(sl, (div_h, div_qn, div_qt, src_c))

        rhs_h = -div_h
        rhs_qn = -div_qn + src_c
        rhs_qt = -div_qt
        if axis == 1:
            return rhs_h, rhs_qn, rhs_qt
        return rhs_h, rhs_qt, rhs_qn

    # ------------------------------------------------------------------ #
    def _rhs(self, h, qx, qy, rain=None):
        hp, qxp, qyp, zp = self._pad(h, qx, qy)
        up = desing_velocity(hp, qxp, self.eps)
        vp = desing_velocity(hp, qyp, self.eps)
        rx_h, rx_qx, rx_qy = self._flux_div(hp, up, vp, zp, axis=1)
        ry_h, ry_qx, ry_qy = self._flux_div(hp, up, vp, zp, axis=0)
        rh = rx_h + ry_h
        if rain is not None:
            rh = rh + rain
        return rh, rx_qx + ry_qx, rx_qy + ry_qy

    # ------------------------------------------------------------------ #
    def compute_dt(self, h, qx, qy, rain=None):
        """CFL timestep, accounting for the depth `rain` adds during the step —
        detached from the graph.

        A dry cell has no wave speed, yet rain wets it within the step and the
        second RK stage then moves water at c = sqrt(g (h + r dt)). Using
        sqrt(a + b) <= sqrt(a) + sqrt(b), the limit becomes
        dt (s + k sqrt(dt)) = cfl with s the plain CFL speed and
        k = sqrt(g r_max) / min(dx, dy). Without rain this is the plain CFL dt.
        """
        with torch.no_grad():
            u = desing_velocity(h, qx, self.eps)
            v = desing_velocity(h, qy, self.eps)
            c = torch.sqrt(self.g * torch.clamp(h, min=0.0))
            sx = ((u.abs() + c) / self.dx).max()
            sy = ((v.abs() + c) / self.dy).max()
            s = torch.maximum(sx, sy)
            if rain is None:
                s, r_max = s.item(), 0.0
            else:   # one host sync for both, see dt_every in run()
                r_max = torch.as_tensor(rain).to(s).max()
                s, r_max = torch.stack((s, r_max)).tolist()
            k = (self.g * max(r_max, 0.0)) ** 0.5 / min(self.dx, self.dy)
            return min(self.dt_max, _cfl_dt(self.cfl, s, k))

    def _friction(self, h, qx, qy, dt):
        u = desing_velocity(h, qx, self.eps)
        v = desing_velocity(h, qy, self.eps)
        sp = safe_sqrt(u ** 2 + v ** 2)   # zero in still water and on dry cells
        h43 = torch.clamp(h, min=self.eps) ** (4.0 / 3.0)
        fac = 1.0 + dt * self.g * self.n ** 2 * sp / h43
        return qx / fac, qy / fac

    def step(self, h, qx, qy, dt=None, rain=None):
        """One SSP-RK2 step. Returns (h, qx, qy, dt_used).

        An explicit dt is taken exactly. With dt=None the step is adaptive:
        compute_dt, then the step_limited backstop, so dt_used may be smaller.
        """
        if dt is None:
            return self.step_limited(h, qx, qy, self.compute_dt(h, qx, qy, rain), rain)
        return (*self._try_step(h, qx, qy, dt, rain)[:3], dt)

    def step_limited(self, h, qx, qy, dt_limit, rain=None):
        """One SSP-RK2 step of at most dt_limit, halved until clipping creates
        no meaningful water. Returns (h, qx, qy, dt_used); callers must advance
        time by dt_used. dt stays a detached float, and rejected attempts just
        drop their graphs, so accepted steps differentiate as a fixed-dt step."""
        dt = dt_limit
        for _ in range(MAX_DT_HALVINGS + 1):
            hn, qxn, qyn, clip = self._try_step(h, qx, qy, dt, rain)
            clip, water = torch.stack((clip, hn.detach().sum())).tolist()
            if clip <= CLIP_TOL * water:
                return hn, qxn, qyn, dt
            dt *= 0.5
            self.n_retries += 1
        raise RuntimeError(f"depths stay negative after halving dt_limit={dt_limit} s "
                           f"{MAX_DT_HALVINGS} times (clipped {clip:.3e} m, water {water:.3e} m)")

    def _try_step(self, h, qx, qy, dt, rain):
        """SSP-RK2 at exactly dt. Returns (h, qx, qy, clip), where clip is the
        detached depth [m, summed over cells] that clamping negative depths
        added to the grid."""
        r1 = self._rhs(h, qx, qy, rain)
        h1 = h + dt * r1[0]
        clip = 0.5 * torch.clamp(-h1.detach(), min=0.0).sum()
        h1 = torch.clamp(h1, min=0.0)
        qx1 = qx + dt * r1[1]
        qy1 = qy + dt * r1[2]
        r2 = self._rhs(h1, qx1, qy1, rain)
        hn = 0.5 * h + 0.5 * (h1 + dt * r2[0])
        clip = clip + torch.clamp(-hn.detach(), min=0.0).sum()
        hn = torch.clamp(hn, min=0.0)
        qxn = 0.5 * qx + 0.5 * (qx1 + dt * r2[1])
        qyn = 0.5 * qy + 0.5 * (qy1 + dt * r2[2])
        qxn, qyn = self._friction(hn, qxn, qyn, dt)
        # kill residual momentum in effectively dry cells
        dry = hn <= self.eps
        qxn = torch.where(dry, torch.zeros_like(qxn), qxn)
        qyn = torch.where(dry, torch.zeros_like(qyn), qyn)
        return hn, qxn, qyn, clip

    def run(self, h, qx, qy, t_end, rain_fn=None, t0=0.0, callback=None,
            checkpoint_every=0, nudge_fn=None, dt_every=1):
        """Integrate to t_end.

        rain_fn : callable t -> (ny, nx) tensor of lateral inflow [m/s]
                  (rainfall excess / EF5 runoff), or None. Must be >= 0: a
                  sink over a dry cell can only be met by clipping, which the
                  step_limited backstop refuses.
        callback : callable (t, h, qx, qy) after each step.
        checkpoint_every : if > 0, wrap every N steps in
                  torch.utils.checkpoint to trade compute for memory when
                  backpropagating through long simulations.
        nudge_fn : callable (t, h) -> h applied after each step — e.g. the
                  EF5ChannelStage floor that couples routed channel flow in.
        dt_every : recompute the CFL dt only every `dt_every` steps and hold
                  0.9x the last computed value in between, trading <=10% step
                  size for compute_dt's passes and device->host sync. Every
                  step, held or not, still syncs once for the step_limited
                  backstop. 1 (default) = exact per-step CFL.

        Time advances by the dt each step actually took, which the backstop
        can make smaller than the CFL dt while rain first wets dry ground.
        """
        t = t0
        nstep = 0
        held_dt = None
        next_change = getattr(rain_fn, "next_change", None)
        while t < t_end - 1e-12:
            rain = rain_fn(t) if rain_fn is not None else None
            if dt_every <= 1 or held_dt is None or nstep % dt_every == 0:
                dt = self.compute_dt(h, qx, qy, rain)
                held_dt = 0.9 * dt
            else:
                dt = held_dt
            if t + dt > t_end:
                dt = t_end - t
            if next_change is not None:
                nc = next_change(t)
                if 1e-9 < nc < dt:
                    dt = nc  # land exactly on the forcing switch
            if checkpoint_every > 0 and h.requires_grad:
                from torch.utils.checkpoint import checkpoint as _ckpt
                # pick dt outside the checkpoint: its replay during backward
                # must retake exactly this dt, not repeat the search
                with torch.no_grad():
                    dt = self.step_limited(h, qx, qy, dt, rain)[3]
                h, qx, qy, _ = _ckpt(self.step, h, qx, qy, dt, rain, use_reentrant=False)
            else:
                h, qx, qy, dt = self.step_limited(h, qx, qy, dt, rain)
            t += dt
            nstep += 1
            if nudge_fn is not None:
                h = nudge_fn(t, h)
            if callback is not None:
                callback(t, h, qx, qy)
        return h, qx, qy
