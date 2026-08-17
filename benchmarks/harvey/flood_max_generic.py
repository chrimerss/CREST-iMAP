"""Running max of water DEPTH over an Inunda run's zarr -> GeoTIFF on the DEM grid.

Generalisation of NN4flood/scripts/harvey_benchmark/flood_max.py (which hard-codes the
10 m resv run) so the 30 m matched-control run can be reduced the same way, and scored
by the same HWM script as the CREST-iMAP v2 output.

  python flood_max_generic.py <run.zarr> <dem.tif> <out.tif>
"""
import sys
import time
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import rasterio
import zarr

ZP, DEM, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

z = zarr.open(ZP, mode="r")
h = z["h"]
T = h.shape[0]
print(f"frames {T}  shape {h.shape}", flush=True)

acc = None
t0 = time.time()
for i in range(T):
    a = np.asarray(h[i]).astype("float32")
    acc = a if acc is None else np.fmax(acc, a)      # fmax ignores nan
    if i % 30 == 0:
        print(f"  frame {i}/{T}  {time.time()-t0:.0f}s", flush=True)
acc = np.where(np.isfinite(acc), acc, np.nan).astype("float32")

with rasterio.open(DEM) as d:
    prof = d.profile.copy()
    assert (d.height, d.width) == acc.shape, \
        f"grid mismatch {(d.height, d.width)} vs {acc.shape}"
prof.update(count=1, dtype="float32", nodata=np.nan, compress="zstd", predictor=2,
            tiled=True, blockxsize=512, blockysize=512)
with rasterio.open(OUT, "w", **prof) as o:
    o.write(acc, 1)
print(f"wrote {OUT}  maxdepth range {np.nanmin(acc):.3f} .. {np.nanmax(acc):.3f}", flush=True)
