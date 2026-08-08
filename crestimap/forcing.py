"""Forcing and initial-condition interface to CREST-AI (EF5/CREST).

In the coupled deployment the CREST water balance is NOT run inside this
package (that was v1.x). Instead the CREST-AI pipeline runs EF5/CREST for
the event window and hands over:

  initial conditions : 2-D discharge (Q) and soil-moisture (SM) grids at
                       event start (channel pre-wetting / antecedent state)
  forcing            : gridded surface runoff (fast flow) + subsurface
                       runoff (interflow/baseflow) per timestep, which enter
                       the shallow-water equations as the lateral-inflow
                       source term [m/s]

EF5 writes GeoTIFF output grids; this module regrids them onto the solver
raster and exposes a `rain_fn(t)`-style callable for `SWESolver.run`.

Status: interface is stable, EF5-file plumbing is experimental until wired
to real CREST-AI event output.
"""
from __future__ import annotations

import bisect
import datetime as _dt

import numpy as np
import torch


class GriddedSeriesForcing:
    """Time series of lateral-inflow grids -> callable(t_seconds) -> tensor.

    Parameters
    ----------
    times : sorted list of datetimes (grid validity times).
    loader : callable(index) -> 2-D numpy array in mm/h on the solver grid.
             (Keep loading lazy: events are long, grids are big.)
    t0 : datetime that corresponds to simulation time t = 0 s.
    hold : if True (default) use the most recent grid at or before t
           (piecewise-constant, mass-consistent with EF5 accumulation);
           if False, linearly interpolate between bracketing grids.
    """

    MM_PER_HOUR_TO_M_PER_S = 1.0 / 3600.0 / 1000.0

    def __init__(self, times, loader, t0, hold=True, device=None, dtype=None):
        self.times = list(times)
        self.loader = loader
        self.t0 = t0
        self.hold = hold
        self.device = device
        self.dtype = dtype or torch.get_default_dtype()
        self._cache = {}

    def _grid(self, i):
        if i not in self._cache:
            arr = np.asarray(self.loader(i), dtype=float)
            self._cache = {i: torch.as_tensor(
                arr * self.MM_PER_HOUR_TO_M_PER_S,
                dtype=self.dtype, device=self.device)}  # keep only latest
        return self._cache[i]

    def __call__(self, t_seconds: float) -> torch.Tensor:
        when = self.t0 + _dt.timedelta(seconds=float(t_seconds))
        i = bisect.bisect_right(self.times, when) - 1
        i = max(0, min(i, len(self.times) - 1))
        if self.hold or i == len(self.times) - 1:
            return self._grid(i)
        span = (self.times[i + 1] - self.times[i]).total_seconds()
        w = ((when - self.times[i]).total_seconds() / span) if span > 0 else 0.0
        return (1 - w) * self._grid(i) + w * self._grid(i + 1)


def sum_forcings(*fns):
    """Combine surface-runoff and subsurface-runoff forcings."""
    def combined(t):
        out = fns[0](t)
        for f in fns[1:]:
            out = out + f(t)
        return torch.clamp(out, min=0.0)
    return combined


def regrid_to_solver(src: np.ndarray, src_transform, dst_shape, dst_transform,
                     src_crs=None, dst_crs=None):
    """Regrid an EF5 output grid onto the solver raster (bilinear).

    Uses rasterio.warp when available; falls back to nearest-neighbor
    index mapping for identical CRS.
    """
    try:
        from rasterio.warp import reproject, Resampling
        dst = np.zeros(dst_shape, dtype=float)
        reproject(source=src.astype(float), destination=dst,
                  src_transform=src_transform, dst_transform=dst_transform,
                  src_crs=src_crs or "EPSG:4326", dst_crs=dst_crs or "EPSG:4326",
                  resampling=Resampling.bilinear)
        return dst
    except ImportError:
        # nearest-neighbor fallback, same CRS only
        ny, nx = dst_shape
        rows, cols = np.mgrid[0:ny, 0:nx]
        xs, ys = dst_transform * (cols + 0.5, rows + 0.5)
        inv = ~src_transform
        sc, sr = inv * (xs, ys)
        sr = np.clip(sr.astype(int), 0, src.shape[0] - 1)
        sc = np.clip(sc.astype(int), 0, src.shape[1] - 1)
        return src[sr, sc].astype(float)


def initial_state_from_ef5(q_grid, sm_grid, dem, dx, dy,
                           bankfull_width_fn=None):
    """Build (h, qx, qy) initial conditions from EF5 2-D Q and SM grids.

    Channel pre-wetting: EF5 discharge Q [m3/s] on the routed network is
    converted to an initial water depth along channel cells via a rating
    approximation h ~ (n Q / (w sqrt(S)))^(3/5); off-channel cells start
    dry. SM enters the CREST-AI side (it conditions the runoff EF5 sends
    us) — kept here for provenance/diagnostics.

    Experimental: exact rating and width model to be calibrated against
    the differentiable solver itself once wired end-to-end.
    """
    q = torch.as_tensor(np.asarray(q_grid, dtype=float))
    h0 = torch.zeros_like(q)
    if bankfull_width_fn is None:
        bankfull_width_fn = lambda qq: torch.clamp(7.2 * qq ** 0.5, min=1.0)  # Leopold-Maddock-ish
    chan = q > 1.0  # m3/s threshold for "channel" cells
    w = bankfull_width_fn(torch.clamp(q, min=0.0))
    n_ch, slope = 0.035, 1e-3
    h_ch = (n_ch * torch.clamp(q, min=0.0) / (w * slope ** 0.5)) ** 0.6
    h0 = torch.where(chan, torch.minimum(h_ch, torch.as_tensor(5.0)), h0)
    return h0, torch.zeros_like(h0), torch.zeros_like(h0)
