"""Analytic reference solutions for solver validation."""
from __future__ import annotations

import numpy as np


def stoker_dambreak(x, t, hl, hr, x0=0.0, g=9.80665):
    """Exact wet-bed dam-break solution (Stoker 1957).

    Initial state: h = hl for x < x0, h = hr (> 0) for x > x0, u = 0.

    Returns (h, u) arrays on `x` at time `t`.
    """
    x = np.asarray(x, dtype=float)
    cl = np.sqrt(g * hl)

    # middle state: rarefaction (left) + shock (right)
    def f(hm):
        return (2.0 * (cl - np.sqrt(g * hm))
                - (hm - hr) * np.sqrt(0.5 * g * (hm + hr) / (hm * hr)))

    lo, hi = hr * (1 + 1e-12), hl * (1 - 1e-12)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    hm = 0.5 * (lo + hi)
    cm = np.sqrt(g * hm)
    um = 2.0 * (cl - cm)
    # shock speed from mass conservation across the shock
    s = hm * um / (hm - hr)

    xi = (x - x0) / max(t, 1e-300)
    h = np.empty_like(x)
    u = np.empty_like(x)

    reg1 = xi <= -cl                      # undisturbed left
    reg2 = (xi > -cl) & (xi <= um - cm)   # rarefaction fan
    reg3 = (xi > um - cm) & (xi <= s)     # middle state
    reg4 = xi > s                         # undisturbed right

    h[reg1] = hl
    u[reg1] = 0.0
    c_fan = (2.0 * cl - xi[reg2]) / 3.0
    h[reg2] = c_fan ** 2 / g
    u[reg2] = 2.0 / 3.0 * (xi[reg2] + cl)
    h[reg3] = hm
    u[reg3] = um
    h[reg4] = hr
    u[reg4] = 0.0
    return h, u
