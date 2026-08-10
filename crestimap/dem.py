"""On-demand 3DEP DEM acquisition — no CONUS DEM archive needed.

Event domains are small (a triggered basin's bbox), so tiles are fetched
from the public USGS 3DEP S3 bucket at simulation time and cached on local
disk only. Storage budget on HF stays zero for terrain; the per-event
clipped DEM (a few MB compressed) may be bundled with the event results
for reproducibility.

res "1"  = 1 arc-second  (~30 m)  ~50 MB per 1x1 degree tile
res "13" = 1/3 arc-second (~10 m) ~400 MB per tile (GPU-class runs)
"""
from __future__ import annotations

import math
import os

import numpy as np

NODATA_MIN = -1e5

_URL_PATTERNS = (
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/{res}/TIFF/current/{t}/USGS_{res}_{t}.tif",
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/{res}/TIFF/{t}/USGS_{res}_{t}.tif",
)


def tile_name(lat0: int, lon0: int) -> str:
    """3DEP tile covering [lat0, lat0+1] x [lon0, lon0+1] (CONUS: lon0 < 0)."""
    return f"n{lat0 + 1:02d}w{-lon0:03d}"


def tiles_for_bbox(w, s, e, n):
    out = []
    for lat0 in range(math.floor(s), max(math.floor(s) + 1, math.ceil(n))):
        for lon0 in range(math.floor(w), max(math.floor(w) + 1, math.ceil(e))):
            out.append(tile_name(lat0, lon0))
    return out


def fetch_tile(t: str, res: str = "1", cache_dir: str = "dem_cache") -> str:
    os.makedirs(cache_dir, exist_ok=True)
    p = os.path.join(cache_dir, f"USGS_{res}_{t}.tif")
    if os.path.exists(p) and os.path.getsize(p) > 1_000_000:
        return p
    import requests
    last = None
    for pat in _URL_PATTERNS:
        url = pat.format(res=res, t=t)
        try:
            r = requests.get(url, stream=True, timeout=180)
            if r.status_code != 200:
                last = f"HTTP {r.status_code} {url}"
                continue
            tmp = p + ".part"
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            os.replace(tmp, p)
            return p
        except requests.RequestException as e:  # try next pattern
            last = f"{type(e).__name__} {url}"
    raise FileNotFoundError(f"3DEP tile {t} (res {res}) unavailable: {last}")


def block_mean(z: np.ndarray, transform, f: int):
    """Aggregate by integer factor f (block mean) — keeps mass/area sanity
    when shrinking the solver grid to a CPU-feasible cell count."""
    from rasterio import Affine
    ny, nx = z.shape
    ny2, nx2 = ny // f, nx // f
    z2 = z[:ny2 * f, :nx2 * f].reshape(ny2, f, nx2, f).mean(axis=(1, 3))
    t2 = Affine(transform.a * f, transform.b, transform.c,
                transform.d, transform.e * f, transform.f)
    return z2.astype(np.float32), t2


def load_dem(bbox, res: str = "1", cache_dir: str = "dem_cache",
             max_cells: int | None = None):
    """Mosaic + clip 3DEP tiles to bbox=(w,s,e,n); optionally block-mean
    downsample so ny*nx <= max_cells. Returns (z float32, transform, crs)."""
    import rasterio
    from rasterio.merge import merge
    w, s, e, n = bbox
    paths = [fetch_tile(t, res, cache_dir) for t in tiles_for_bbox(w, s, e, n)]
    srcs = [rasterio.open(p) for p in paths]
    try:
        arr, tr = merge(srcs, bounds=(w, s, e, n))
        crs = srcs[0].crs
    finally:
        for d in srcs:
            d.close()
    z = arr[0].astype(np.float32)
    bad = ~np.isfinite(z) | (z < NODATA_MIN)
    if bad.any():
        z = np.where(bad, np.nanmin(np.where(bad, np.nan, z)), z)
    if max_cells and z.size > max_cells:
        f = math.ceil(math.sqrt(z.size / max_cells))
        z, tr = block_mean(z, tr, f)
    return z, tr, crs
