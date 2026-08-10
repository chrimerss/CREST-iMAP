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
- SSP-RK2 (Heun) time stepping, adaptive CFL timestep (detached from the
  autograd graph so gradients stay well defined).
- Point-implicit Manning friction (closed form, differentiable).
- Desingularized velocities u = sqrt(2) h q / sqrt(h^4 + max(h,eps)^4)
  (Kurganov & Petrova 2007) so wet/dry fronts neither blow up nor produce
  NaN gradients.
- Lateral inflow source term `rain` (m/s): rainfall excess or, in the
  CREST-AI coupling, EF5/CREST surface + subsurface runoff grids.

Everything is expressed as torch tensor ops, so the entire simulation is
differentiable end to end w.r.t. Manning n, bed elevation z, initial
conditions, and forcing.
"""
from __future__ import annotations

import torch

G_DEFAULT = 9.80665


def desing_velocity(h: torch.Tensor, q: torch.Tensor, eps: float) -> torch.Tensor:
    """Desingularized velocity u = sqrt(2) h q / sqrt(h^4 + max(h,eps)^4)."""
    h4 = h ** 4
    e4 = torch.clamp(h, min=eps) ** 4
    return (2.0 ** 0.5) * h * q / torch.sqrt(h4 + e4)


def minmod(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    return 0.5 * (torch.sign(a) + torch.sign(b)) * torch.minimum(a.abs(), b.abs())


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
        self.cfl = cfl
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

        cm = torch.sqrt(g * hms)
        cp = torch.sqrt(g * hps)
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
    def compute_dt(self, h, qx, qy):
        """CFL timestep — detached from the graph."""
        with torch.no_grad():
            u = desing_velocity(h, qx, self.eps)
            v = desing_velocity(h, qy, self.eps)
            c = torch.sqrt(self.g * torch.clamp(h, min=0.0))
            sx = ((u.abs() + c) / self.dx).max()
            sy = ((v.abs() + c) / self.dy).max()
            s = torch.maximum(sx, sy)
            if s < 1e-12:
                return self.dt_max
            return min(self.dt_max, (self.cfl / s).item())

    def _friction(self, h, qx, qy, dt):
        u = desing_velocity(h, qx, self.eps)
        v = desing_velocity(h, qy, self.eps)
        sp = torch.sqrt(u ** 2 + v ** 2)
        h43 = torch.clamp(h, min=self.eps) ** (4.0 / 3.0)
        fac = 1.0 + dt * self.g * self.n ** 2 * sp / h43
        return qx / fac, qy / fac

    def step(self, h, qx, qy, dt=None, rain=None):
        """One SSP-RK2 step. Returns (h, qx, qy, dt_used)."""
        if dt is None:
            dt = self.compute_dt(h, qx, qy)
        r1 = self._rhs(h, qx, qy, rain)
        h1 = torch.clamp(h + dt * r1[0], min=0.0)
        qx1 = qx + dt * r1[1]
        qy1 = qy + dt * r1[2]
        r2 = self._rhs(h1, qx1, qy1, rain)
        hn = torch.clamp(0.5 * h + 0.5 * (h1 + dt * r2[0]), min=0.0)
        qxn = 0.5 * qx + 0.5 * (qx1 + dt * r2[1])
        qyn = 0.5 * qy + 0.5 * (qy1 + dt * r2[2])
        qxn, qyn = self._friction(hn, qxn, qyn, dt)
        # kill residual momentum in effectively dry cells
        dry = hn <= self.eps
        qxn = torch.where(dry, torch.zeros_like(qxn), qxn)
        qyn = torch.where(dry, torch.zeros_like(qyn), qyn)
        return hn, qxn, qyn, dt

    def run(self, h, qx, qy, t_end, rain_fn=None, t0=0.0, callback=None,
            checkpoint_every=0):
        """Integrate to t_end.

        rain_fn : callable t -> (ny, nx) tensor of lateral inflow [m/s]
                  (rainfall excess / EF5 runoff), or None.
        callback : callable (t, h, qx, qy) after each step.
        checkpoint_every : if > 0, wrap every N steps in
                  torch.utils.checkpoint to trade compute for memory when
                  backpropagating through long simulations.
        """
        t = t0
        nstep = 0
        next_change = getattr(rain_fn, "next_change", None)
        while t < t_end - 1e-12:
            rain = rain_fn(t) if rain_fn is not None else None
            dt = self.compute_dt(h, qx, qy)
            if t + dt > t_end:
                dt = t_end - t
            if next_change is not None:
                nc = next_change(t)
                if 1e-9 < nc < dt:
                    dt = nc  # land exactly on the forcing switch
            if checkpoint_every > 0 and h.requires_grad:
                from torch.utils.checkpoint import checkpoint as _ckpt
                h, qx, qy, _ = _ckpt(
                    lambda a, b, c: self.step(a, b, c, dt=dt, rain=rain),
                    h, qx, qy, use_reentrant=False)
            else:
                h, qx, qy, _ = self.step(h, qx, qy, dt=dt, rain=rain)
            t += dt
            nstep += 1
            if callback is not None:
                callback(t, h, qx, qy)
        return h, qx, qy
