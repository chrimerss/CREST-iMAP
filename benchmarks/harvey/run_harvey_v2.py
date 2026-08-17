"""CREST-iMAP v2 on Hurricane Harvey, Harris County TX.

Configuration under test: the CREST/EF5 hydrologic layer is KEPT (`crestimap.lsm.
CrestLSM` -- the same VIC-curve water balance v1 runs in-loop, verified bit-identical
to v1's Cython `crest_simp.pyx`), and ONLY the dynamic core is replaced by the v2
PyTorch well-balanced HLL solver (`crestimap.solver.SWESolver`).

Everything else is held identical to the benchmarked Inunda run (conf/harvey10m_resv
.yaml + conf/harris30m.yaml) so the comparison isolates the hydrodynamic core:

  * DEM        HCFCD channel-preserving, 3x block-mean to 30 m, EPSG:32615, NAVD88.
               nodata neighbour-filled exactly as `inunda.utils.load_dem` does.
  * Manning    NLCD-2019 derived 30 m raster (spatially varying, same crop).
  * Rain       MRMS MultiSensor_QPE_01H hourly, nearest-cell crosswalk gather.
  * Losses     CREST water balance (wm/b/im/ksat EF5 grids) + run-on re-infiltration.
  * Outer BC   wall / noflow  (Inunda default SWE.boundary_mode, enclosed-basin test).

Outputs a peak-depth GeoTIFF on the model grid, scored later at the 813 USGS Harvey
high-water marks by the same script that scores Inunda / Fathom / CREST-iMAP v1.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

import numpy as np
import rasterio
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crestimap.lsm import CrestLSM                       # noqa: E402  (CREST layer)
from crestimap.solver import SWESolver                   # noqa: E402  (v2 dynamic core)

IN = "/scratch/users/li1995/harris30m/input"
MM_PER_H_TO_M_PER_S = 1.0 / 1000.0 / 3600.0


def load_dem(file_path):
    """DEM + validity mask, with nodata filled from the nearest VALID cell.

    Byte-for-byte the same treatment as `inunda.utils.load_dem` (single-pass
    Euclidean distance transform), so the two arms of the benchmark see an
    identical bed. Filling from real neighbouring terrain — rather than zeros or a
    constant — keeps the bed free of cliffs at nodata holes, which would otherwise
    inject spurious momentum at the county boundary.
    """
    with rasterio.open(file_path) as src:
        dem = src.read(1).astype("float32")
        transform, crs, nodata = src.transform, src.crs, src.nodata
    invalid = ~np.isfinite(dem)
    if nodata is not None:
        invalid |= (dem == nodata)
    if invalid.any() and not invalid.all():
        from scipy import ndimage
        idx = ndimage.distance_transform_edt(invalid, return_distances=False,
                                             return_indices=True)
        dem[invalid] = dem[tuple(idx[:, invalid])]
        print(f"[load_dem] filled {int(invalid.sum())} nodata/NaN cells from "
              f"neighbours ({100.0 * invalid.mean():.3f}%)")
    return dem.astype("float32"), transform, crs, ~invalid


# --------------------------------------------------------------------------- #
# forcing: MRMS hourly QPE -> model grid, via a nearest-cell crosswalk gather
# --------------------------------------------------------------------------- #
def build_crosswalk(dem_transform, dem_crs, shape, src_path):
    """Flat int64 index mapping every model cell to the source pixel containing its
    centre (same construction as inunda.landsurface.crest._load_params)."""
    from pyproj import Transformer
    H, W = shape
    A = dem_transform
    with rasterio.open(src_path) as s:
        inv, src_crs, ph, pw = ~s.transform, s.crs, s.height, s.width
    tr = Transformer.from_crs(dem_crs, src_crs, always_xy=True)
    col = np.arange(W) + 0.5
    idx = np.empty(H * W, np.int64)
    for r0 in range(0, H, 1024):
        row = np.arange(r0, min(H, r0 + 1024)) + 0.5
        X = A.c + col[None, :] * A.a + row[:, None] * A.b
        Y = A.f + col[None, :] * A.d + row[:, None] * A.e
        lon, lat = tr.transform(X, Y)
        cm, rm = inv * (lon, lat)
        rm = np.clip(np.floor(rm), 0, ph - 1).astype(np.int64)
        cm = np.clip(np.floor(cm), 0, pw - 1).astype(np.int64)
        idx[r0 * W:(r0 + row.size) * W] = (rm * pw + cm).ravel()
    return idx


class MRMSRain:
    """Hourly MRMS QPE gathered onto the model grid.

    MultiSensor_QPE_01H is an accumulation ENDING at its stamp, so the file stamped
    HH covers (HH-1, HH]  -- `stamp='end'`, per conf/harris30m.yaml. Returns a
    precipitation RATE field in m/s, masked to the valid DEM basin.
    """

    def __init__(self, mrms_dir, t0, t_end, transform, crs, shape, valid, device):
        import glob
        self.files = {}
        for p in sorted(glob.glob(os.path.join(mrms_dir, "qpe_*.tif"))):
            stamp = os.path.basename(p)[4:-4]
            self.files[dt.datetime.strptime(stamp, "%Y%m%d%H")] = p
        self.t0 = t0
        self.idx = torch.from_numpy(
            build_crosswalk(transform, crs, shape, next(iter(self.files.values())))).to(device)
        self.shape = shape
        self.valid = valid
        self.device = device
        self._cache_hour = None
        self._cache = None

    def rate(self, hour_end: dt.datetime) -> torch.Tensor:
        """Precip rate (m/s) for the hour ENDING at `hour_end`."""
        if hour_end == self._cache_hour:
            return self._cache
        p = self.files.get(hour_end)
        if p is None:
            out = torch.zeros(self.shape, dtype=torch.float32, device=self.device)
        else:
            with rasterio.open(p) as ds:
                a = ds.read(1).astype("float32")
                nod = ds.nodata
            bad = ~np.isfinite(a)
            if nod is not None and np.isfinite(nod):
                bad |= (a == nod)
            a = np.where(bad, 0.0, np.clip(a, 0.0, None))          # mm over the hour
            flat = torch.from_numpy(a.ravel()).to(self.device)
            out = flat[self.idx].reshape(self.shape) * MM_PER_H_TO_M_PER_S
            out = out * self.valid
        self._cache_hour, self._cache = hour_end, out
        return out


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2017-08-22T00")
    ap.add_argument("--end", default="2017-09-01T00")
    ap.add_argument("--out", default="/scratch/users/li1995/harris30m/v2_harvey")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--order", type=int, default=2)
    ap.add_argument("--dt-every", type=int, default=1)
    ap.add_argument("--cfl", type=float, default=0.45)
    ap.add_argument("--dt-max", type=float, default=60.0)
    ap.add_argument("--probe-steps", type=int, default=0,
                    help="if >0: run only this many steps and report throughput")
    ap.add_argument("--runon", type=int, default=1)
    ap.add_argument("--init-saturation", type=float, default=0.5)
    ap.add_argument("--frames", type=int, default=0, help="also write hourly depth frames")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    dev = torch.device(args.device)
    torch.backends.cuda.matmul.allow_tf32 = True

    t0 = dt.datetime.strptime(args.start, "%Y-%m-%dT%H")
    t_end = dt.datetime.strptime(args.end, "%Y-%m-%dT%H")
    total_s = (t_end - t0).total_seconds()

    # ---- terrain (identical nodata fill to Inunda) ------------------------- #
    dem_path = os.path.join(IN, "dem_30m.tif")
    z_np, transform, crs, valid_np = load_dem(dem_path)
    ny, nx = z_np.shape
    z = torch.from_numpy(z_np).to(dev)
    valid = torch.from_numpy(valid_np.astype("float32")).to(dev)
    print(f"[grid] {ny}x{nx} = {ny*nx/1e6:.2f}M cells, {valid_np.sum()/1e6:.2f}M valid "
          f"({100*valid_np.mean():.1f}%), dx=30 m, crs={crs}")

    # ---- Manning (spatially varying NLCD-2019) ---------------------------- #
    with rasterio.open(os.path.join(IN, "manning_30m.tif")) as ds:
        n_np = ds.read(1).astype("float32")
    n_np = np.where(np.isfinite(n_np) & (n_np > 0), n_np, 0.05)
    n_t = torch.from_numpy(n_np).to(dev)
    print(f"[manning] range [{n_np.min():.3f}, {n_np.max():.3f}] mean {n_np.mean():.3f}")

    # ---- CREST water balance (the hydrologic layer we KEEP) --------------- #
    crest = CrestLSM.from_grids(
        {k: os.path.join(IN, "crest_params", f"{k}.tif")
         for k in ("wm", "b", "im", "ksat")},
        transform, crs, (ny, nx), device=str(dev),
        init_saturation=args.init_saturation, ke=1.0, pet_rate_ms=0.0)
    print(f"[crest] WM {float(crest.WM.mean()):.0f}mm  B {float(crest.B.mean()):.2f}  "
          f"IM {float(crest.IM.mean()):.2f}  Ksat {float(crest.Ksat.mean()):.1f}mm/h "
          f"(per-cell, crosswalk gather)")

    # ---- rainfall --------------------------------------------------------- #
    rain_src = MRMSRain(os.path.join(IN, "mrms"), t0, t_end, transform, crs,
                        (ny, nx), valid, dev)

    # hourly CREST partition: precip -> overland runoff, cached for the whole hour
    state = {"hour": -1, "runoff": torch.zeros((ny, nx), dtype=torch.float32, device=dev),
             "rain_mm": 0.0, "runoff_mm": 0.0, "runon_mm": 0.0}

    def rain_fn(t):
        hr = int(t // 3600.0)
        if hr != state["hour"]:
            state["hour"] = hr
            hour_end = t0 + dt.timedelta(hours=hr + 1)      # accumulation ending stamp
            precip = rain_src.rate(hour_end)
            ro = crest.step(precip, 3600.0) * valid
            state["runoff"] = ro
            state["rain_mm"] += float(precip.mean()) * 3600.0 * 1000.0
            state["runoff_mm"] += float(ro.mean()) * 3600.0 * 1000.0
        return state["runoff"]

    rain_fn.next_change = lambda t: (int(t // 3600.0) + 1) * 3600.0 - t

    # ---- run-on re-infiltration (LSM.crest.runon: true) ------------------- #
    # Ponded/flowing surface water keeps infiltrating: at each hourly coupling step
    # remove min(h, runon_rate*3600) from the surface and credit it to soil moisture.
    nudge = None
    if args.runon:
        rstate = {"hour": -1}

        def nudge_fn(t, h):
            hr = int(t // 3600.0)
            if hr == rstate["hour"]:
                return h
            rstate["hour"] = hr
            take = torch.minimum(h, crest.runon_rate(3600.0) * 3600.0 * valid)
            crest.absorb(take)
            state["runon_mm"] += float(take.mean()) * 1000.0
            return h - take
        nudge = nudge_fn

    # ---- v2 dynamic core -------------------------------------------------- #
    solver = SWESolver(z, dx=30.0, dy=30.0, n_manning=n_t, order=args.order,
                       bc="wall", cfl=args.cfl, dt_max=args.dt_max)

    h = torch.zeros((ny, nx), dtype=torch.float32, device=dev)
    qx = torch.zeros_like(h)
    qy = torch.zeros_like(h)

    # well-balancedness check on the real DEM: a flat resting lake must not move
    lake = torch.clamp(torch.tensor(2.0, device=dev) - z, min=0.0)
    l1, _, _ = solver.step(lake.clone(), torch.zeros_like(h), torch.zeros_like(h),
                           dt=1.0)[:3]
    print(f"[C-property] lake-at-rest residual on this DEM: "
          f"max |dh| = {float((l1 - lake).abs().max()):.3e} m")
    del lake, l1

    maxd = torch.zeros_like(h)
    nsteps = {"n": 0}
    t_wall0 = time.time()
    log_every = 2000

    out_tif = os.path.join(args.out, "maxdepth_v2_30m.tif")

    def write_maxdepth(path, arr):
        a = np.where(valid_np, arr, np.nan).astype("float32")
        with rasterio.open(path, "w", driver="GTiff", height=ny, width=nx, count=1,
                           dtype="float32", crs=crs, transform=transform,
                           nodata=np.nan, compress="deflate", predictor=3,
                           tiled=True) as ds:
            ds.write(a, 1)

    # periodic checkpoint: a multi-hour run must not lose everything if it is killed
    ckpt = {"next": 24 * 3600.0}

    def cb(t, hh, qqx, qqy):
        nonlocal maxd
        maxd = torch.maximum(maxd, hh)
        nsteps["n"] += 1
        if t >= ckpt["next"]:
            write_maxdepth(out_tif + ".partial", maxd.detach().cpu().numpy())
            print(f"[ckpt] maxdepth checkpoint at sim t={t/3600:.1f} h", flush=True)
            while ckpt["next"] <= t:
                ckpt["next"] += 24 * 3600.0
        if nsteps["n"] % log_every == 0:
            el = time.time() - t_wall0
            frac = t / total_s
            eta = el / max(frac, 1e-9) - el
            print(f"[run] step {nsteps['n']:>8}  sim {t/3600:7.2f} h "
                  f"({100*frac:5.1f}%)  wall {el/60:6.1f} min  ETA {eta/60:6.1f} min  "
                  f"wet {float((hh>0.05).float().mean())*100:4.1f}%  "
                  f"max h {float(hh.max()):5.2f} m", flush=True)
            if args.probe_steps and nsteps["n"] >= args.probe_steps:
                raise KeyboardInterrupt

    if args.probe_steps:
        log_every = max(1, args.probe_steps // 4)

    print(f"[run] integrating {total_s/3600:.0f} h  ({t0} -> {t_end} UTC), "
          f"order={args.order} cfl={args.cfl} dt_every={args.dt_every} "
          f"device={dev} dtype=float32", flush=True)
    try:
        h, qx, qy = solver.run(h, qx, qy, t_end=total_s, rain_fn=rain_fn,
                               callback=cb, nudge_fn=nudge, dt_every=args.dt_every)
    except KeyboardInterrupt:
        print("[probe] stopped early")
    wall = time.time() - t_wall0

    if torch.cuda.is_available():
        print(f"[mem] peak CUDA {torch.cuda.max_memory_allocated()/2**30:.2f} GiB")
    print(f"[done] {nsteps['n']} steps in {wall/60:.2f} min "
          f"({wall/max(nsteps['n'],1)*1e3:.2f} ms/step)")
    print(f"[mass] domain-mean rain {state['rain_mm']:.1f} mm, "
          f"CREST overland {state['runoff_mm']:.1f} mm, "
          f"run-on reinfiltrated {state['runon_mm']:.1f} mm")

    if args.probe_steps:
        sim_done = nsteps["n"] and (nsteps["n"] / max(nsteps["n"], 1))
        return

    # ---- write peak depth ------------------------------------------------- #
    md_raw = maxd.detach().cpu().numpy().astype("float32")
    write_maxdepth(out_tif, md_raw)
    md = np.where(valid_np, md_raw, np.nan)
    meta = {
        "model": "CREST-iMAP v2 (CREST LSM + v2 well-balanced HLL core)",
        "grid": [ny, nx], "dx_m": 30.0, "crs": str(crs),
        "window": [args.start, args.end], "order": args.order, "cfl": args.cfl,
        "dt_every": args.dt_every, "bc": "wall", "runon": bool(args.runon),
        "steps": nsteps["n"], "wall_seconds": wall, "device": str(dev),
        "peak_mem_GiB": (torch.cuda.max_memory_allocated() / 2**30
                         if torch.cuda.is_available() else None),
        "mass_mm": {k: state[k] for k in ("rain_mm", "runoff_mm", "runon_mm")},
    }
    with open(os.path.join(args.out, "run_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[out] {out_tif}")
    print(f"[out] wet cells (>5 cm): {int(np.nansum(md > 0.05))}, "
          f"max depth {np.nanmax(md):.2f} m")


if __name__ == "__main__":
    main()
