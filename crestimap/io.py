"""Compact depth rasters for storage-limited hosting (HF datasets).

Flood-depth fields are mostly dry, so uint16 centimeters + DEFLATE
compresses to a few percent of float32 — an event's whole frame stack
lands in the tens of MB instead of GB. Depth precision 1 cm, range
0–655.35 m.
"""
from __future__ import annotations

import numpy as np


def write_depth(path, depth_m, transform, crs):
    import rasterio
    d = np.clip(np.asarray(depth_m, dtype=float), 0.0, 655.35)
    q = np.round(d * 100.0).astype(np.uint16)
    with rasterio.open(path, "w", driver="GTiff",
                       height=q.shape[0], width=q.shape[1], count=1,
                       dtype="uint16", crs=crs, transform=transform,
                       compress="deflate", predictor=2, tiled=True,
                       blockxsize=256, blockysize=256) as ds:
        ds.write(q, 1)
    return path


def read_depth(path):
    import rasterio
    with rasterio.open(path) as ds:
        return ds.read(1).astype(float) / 100.0, ds.transform, ds.crs
