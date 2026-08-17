"""CREST water balance — the hydrologic layer of CREST-iMAP.

v2's solver is pure hydrodynamics; this module restores the other half of
CREST-iMAP, so the package is again the *coupled* hydrologic–hydraulic model the
v1 papers describe rather than a bare shallow-water solver.

It is a torch port of the v1 cell water balance (`cresthh/crest/crest_simp.pyx`,
Li et al. 2021 EMS): a VIC-style variable-infiltration-curve partition of
precipitation into infiltration-excess **surface runoff** and soil storage, with a
saturated-conductivity interflow term and a per-cell soil-moisture state. The port
is verified bit-identical to the v1 Cython routine (max |diff| ~1e-16 m over 4000
random parameter/forcing combinations — `crestimap/tests/test_lsm.py`).

Two couplings from v1 are carried over because they matter for extreme events:

* **run-on re-infiltration** (`runon_rate` / `absorb`) — ponded and flowing surface
  water keeps infiltrating. Li et al. (2022, EMS 155:105450) showed that ignoring
  it materially changes Texas Gulf Coast inundation.
* **baseflow** (`baseflow_rate`) — optionally banks the interflow into a per-cell
  linear reservoir and returns it to the surface with an e-folding lag, instead of
  discarding it at the cell.

Unlike v1, which called the scalar Cython routine once per centroid through
``numpy.apply_along_axis``, this runs the whole grid as tensor ops: it is
vectorised, runs on GPU, and is differentiable end to end alongside the solver.

Units — WM mm, Ksat mm/h, B and IM dimensionless, SM metres, rates m/s.
"""
from __future__ import annotations

import math

import torch

# Physical parameter envelope. The EF5 soil grids carry non-physical tails (WM up
# to ~2500 mm) that suppress runoff for flashy events, so clamp on ingest. B's
# ceiling is set by the data, not by the "typical" range: both EF5 parameter grids
# top out at exactly 11.55 and both operational EF5 configs use them at face value.
CREST_PARAM_BOUNDS = {
    "wm": (20.0, 500.0),
    "b": (0.05, 12.0),
    "im": (0.0, 0.999999),
    "ksat": (0.0, 117.8),
}
KE_RANGE = (0.2, 2.0)
IWU_RANGE = (0.0, 1.0)


def crest_core(precip, adjpet, SM, WM, B, IM, Ksat, step_hour):
    """One CREST water-balance step on mm-unit tensors.

    Tensor-in / tensor-out (so it is ``torch.compile``-able and differentiable).
    Returns ``(overland_mm, Wo_mm, interflow_mm)`` — surface runoff, updated soil
    moisture, and the subsurface interflow for the step. ``adjpet`` and
    ``step_hour`` may be Python floats.
    """
    b1 = 1.0 + B
    SMc = torch.minimum(SM, WM)                     # cap at capacity for the VIC curve
    pminuspet = torch.clamp(precip - adjpet, min=0.0)

    # ---- wet branch: infiltration excess via the VIC curve ---- #
    precip_soil = pminuspet * (1.0 - IM)
    precip_imperv = pminuspet * IM
    Wmaxm = WM * b1
    A = Wmaxm * (1.0 - torch.pow(torch.clamp(1.0 - SMc / WM, min=0.0), 1.0 / b1))
    sat = (precip_soil + A) >= Wmaxm
    R_sat = torch.clamp(precip_soil - (WM - SMc), min=0.0)
    base1 = torch.clamp(1.0 - A / Wmaxm, min=0.0)
    base2 = torch.clamp(1.0 - (A + precip_soil) / Wmaxm, min=0.0)
    infil = WM * (torch.pow(base1, b1) - torch.pow(base2, b1))
    infil = torch.minimum(infil, precip_soil)
    R_unsat = torch.clamp(precip_soil - infil, min=0.0)
    R = torch.where(sat, R_sat, R_unsat)
    Wo_wet = torch.where(sat, WM, SMc + infil)
    # interflow reduces surface runoff (as in v1) and is banked or discarded above
    temX = (SMc + Wo_wet) / WM / 2.0 * Ksat * step_hour
    interflow = torch.minimum(R, temX)
    overland_wet = R - interflow + precip_imperv

    # ---- dry branch: ET depletes the soil, no runoff ---- #
    excess_et = torch.clamp(adjpet - precip, min=0.0) * SMc / WM
    Wo_dry = torch.clamp(SMc - excess_et, min=0.0)

    wet = precip > adjpet
    zero = torch.zeros_like(overland_wet)
    return (torch.where(wet, overland_wet, zero),
            torch.where(wet, Wo_wet, Wo_dry),
            torch.where(wet, interflow, zero))


class CrestLSM:
    """Per-cell CREST water balance over the model grid.

    Holds the static parameter tensors and the soil-moisture state, and converts a
    precipitation **rate** field into a surface-runoff **rate** field. Call it at
    the forcing cadence (e.g. hourly); the solver consumes the returned field as
    its lateral-inflow source term.

    >>> lsm = CrestLSM(WM, B, IM, Ksat, init_saturation=0.5, device="cuda")
    >>> runoff_ms = lsm.step(precip_ms, 3600.0)        # -> SWESolver rain_fn
    """

    def __init__(self, WM, B, IM, Ksat, ke=1.0, pet_rate_ms=0.0,
                 init_saturation=0.5, device="cpu", bounds=None, baseflow=None,
                 dtype=torch.float32):
        bnd = {**CREST_PARAM_BOUNDS, **(bounds or {})}
        as_t = lambda a: (a if torch.is_tensor(a) else torch.as_tensor(a)).to(
            device=device, dtype=dtype)
        self.WM = torch.clamp(as_t(WM), *bnd["wm"])
        self.B = torch.clamp(as_t(B), *bnd["b"])
        self.IM = torch.clamp(as_t(IM), *bnd["im"])
        self.Ksat = torch.clamp(as_t(Ksat), *bnd["ksat"])
        self.KE = float(min(max(ke, KE_RANGE[0]), KE_RANGE[1]))
        self.pet_ms = float(pet_rate_ms)
        sat0 = float(min(max(init_saturation, IWU_RANGE[0]), IWU_RANGE[1]))
        self.SM = sat0 * self.WM / 1000.0                       # metres
        self.device, self.dtype = device, dtype

        bf = dict(baseflow or {})
        self.bf_enabled = bool(bf.get("enabled", False))
        # tau floors at 60 s: a guard on exp(-dt/tau), not a physics limit.
        self.bf_tau = max(60.0, float(bf.get("tau_hours", 24.0)) * 3600.0)
        self.bf_frac = float(min(max(float(bf.get("frac", 1.0)), 0.0), 1.0))
        self.RS = torch.zeros_like(self.SM) if self.bf_enabled else None

    @torch.no_grad()
    def step(self, precip_ms, dt_seconds):
        """Advance the soil state by ``dt_seconds``; return overland runoff [m/s]."""
        dt = float(dt_seconds)
        precip = precip_ms * (dt * 1000.0)                      # mm over the step
        adjpet = self.pet_ms * dt * 1000.0 * self.KE            # mm
        overland_mm, Wo_mm, interflow_mm = crest_core(
            precip, adjpet, self.SM * 1000.0,
            self.WM, self.B, self.IM, self.Ksat, dt / 3600.0)
        self.SM = Wo_mm / 1000.0
        if self.bf_enabled:
            self.RS.add_(interflow_mm, alpha=self.bf_frac / 1000.0)
        return overland_mm / 1000.0 / dt

    # ---- interflow -> lagged surface return -------------------------------- #
    @torch.no_grad()
    def baseflow_rate(self, dt_seconds):
        """Release rate [m/s] for the next interval; decays the reservoir.

        Exact linear-reservoir discretisation: over an interval with no recharge
        ``S(t+dt) = S e^(-dt/tau)``, so the released depth is ``S (1 - e^(-dt/tau))``
        — unconditionally stable and mass-exact at any dt.
        """
        if not self.bf_enabled:
            return torch.zeros_like(self.SM)
        dt = float(dt_seconds)
        decay = math.exp(-dt / self.bf_tau)
        released = self.RS * (1.0 - decay)
        self.RS.mul_(decay)
        return released / dt

    # ---- run-on (re-)infiltration ------------------------------------------ #
    @torch.no_grad()
    def runon_rate(self, dt_seconds):
        """Infiltration capacity left for PONDED surface water over the next
        interval [m/s]: Ksat-limited and storage-limited, pervious fraction only."""
        dt = float(dt_seconds)
        cap_m = torch.clamp(self.WM / 1000.0 - self.SM, min=0.0)
        ksat_ms = self.Ksat / 1000.0 / 3600.0
        return torch.minimum(ksat_ms, cap_m / dt) * (1.0 - self.IM)

    @torch.no_grad()
    def absorb(self, depth_m):
        """Credit ponded water removed by the run-on sink into soil moisture."""
        self.SM = torch.clamp(self.SM + depth_m, max=self.WM / 1000.0)

    # ------------------------------------------------------------------ #
    @classmethod
    def from_grids(cls, paths, transform, crs, shape, device="cpu", **kw):
        """Build from EF5/CREST parameter rasters (``{'wm':path, 'b':..., 'im':...,
        'ksat':...}``), gathering each onto the model grid via a nearest-cell
        crosswalk — the parameter grids are far coarser than the DEM."""
        grids = _gather_params(paths, transform, crs, shape, device)
        IM = grids["im"]
        # EF5 publishes imperviousness in PERCENT; operational configs pair the grid
        # with the scalar im=0.01. Rescale a grid that is clearly still percent.
        if float(IM.max()) > 1.5:
            IM = IM / 100.0
        return cls(grids["wm"], grids["b"], IM, grids["ksat"], device=device, **kw)


def _gather_params(paths, transform, crs, shape, device):
    """Nearest-cell gather of coarse parameter rasters onto the model grid.

    The expensive part (the per-cell reprojection index) is built once per unique
    source grid and reused, so a co-registered parameter set costs one index.
    """
    import numpy as np
    import rasterio
    from pyproj import Transformer

    H, W = shape
    A = transform
    col = np.arange(W) + 0.5
    index_cache, out = {}, {}
    defaults = {"wm": 100.0, "b": 1.0, "im": 0.0, "ksat": 1.0}
    for key, path in paths.items():
        with rasterio.open(path) as s:
            arr = s.read(1).astype("float32")
            nod, inv, src_crs = s.nodata, ~s.transform, s.crs
            ph, pw = s.height, s.width
            sig = (s.transform.to_gdal(), src_crs.to_wkt() if src_crs else "", ph, pw)
        valid = np.isfinite(arr)
        if nod is not None and not (isinstance(nod, float) and np.isnan(nod)):
            valid &= (arr != nod)
        fill = float(np.median(arr[valid])) if valid.any() else defaults.get(key, 0.0)
        flat = np.where(valid, arr, fill).astype("float32").ravel()
        if sig not in index_cache:
            tr = Transformer.from_crs(crs, src_crs, always_xy=True)
            idx = np.empty(H * W, np.int64)
            for r0 in range(0, H, 1024):                  # row chunks bound memory
                row = np.arange(r0, min(H, r0 + 1024)) + 0.5
                X = A.c + col[None, :] * A.a + row[:, None] * A.b
                Y = A.f + col[None, :] * A.d + row[:, None] * A.e
                lon, lat = tr.transform(X, Y)
                cm, rm = inv * (lon, lat)
                rm = np.clip(np.floor(rm), 0, ph - 1).astype(np.int64)
                cm = np.clip(np.floor(cm), 0, pw - 1).astype(np.int64)
                idx[r0 * W:(r0 + row.size) * W] = (rm * pw + cm).ravel()
            index_cache[sig] = idx
        gathered = flat[index_cache[sig]].reshape(H, W)
        out[key] = torch.from_numpy(gathered).to(device)
    return out
