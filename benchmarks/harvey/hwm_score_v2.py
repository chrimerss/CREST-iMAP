"""Score CREST-iMAP v2 at the 813 USGS Harvey high-water marks, alongside the
models already in the Inunda SOTA table.

Method is IDENTICAL to NN4flood/scripts/harvey_benchmark/hwm_headtohead.py (so the
new row is directly comparable to the published ones): each model's PEAK DEPTH is
sampled at the HWM location (nearest cell, each raster in its own CRS) and compared
against the HWM's surveyed `height_above_gnd` — terrain-independent.

Coverage / nodata rules (a dry in-domain cell counts as depth 0 = a potential miss;
only genuinely out-of-model cells are skipped):
  * Inunda        EPSG:32615, 10 m, m      : nan -> dry 0 (full Harris domain)
  * CREST-iMAP v2 EPSG:32615, 30 m, m      : nan = outside county mask -> skip
  * Fathom        EPSG:4326, 30 m, m       : 999 = permanent water/nodata -> skip
  * CREST-iMAP v1 EPSG:4326, ~10 m, m      : Houston-core box only; -9999 -> dry 0
"""
import warnings; warnings.filterwarnings("ignore")
import csv
import json
import os
import sys

import numpy as np
import rasterio
from rasterio.warp import transform as wt
from rasterio.windows import Window

HWM = "/scratch/users/li1995/harris10m/harvey_hwm_harris.csv"
INUN = "/scratch/users/li1995/harris10m/harvey10m_resv_maxdepth.tif"
FATHOM = "/scratch/users/li1995/harris10m/fathom_harvey_baseline.tif"
CRESTV1 = "/scratch/users/li1995/harris10m/crest_imap/max_depth_CREST_iMAP.tif"
CRESTV2 = os.environ.get(
    "CRESTV2_TIF", "/scratch/users/li1995/harris30m/v2_harvey/maxdepth_v2_30m.tif")
# matched-resolution control: Inunda's local-inertial core on the IDENTICAL 30 m grid,
# forcing, CREST layer, window and wall BC (conf/harris30m_v2cmp.yaml)
INUN30 = os.environ.get(
    "INUNDA30_TIF", "/scratch/users/li1995/harris30m/v2_harvey/maxdepth_inunda30m.tif")
OUT_CSV = "/scratch/users/li1995/harris30m/v2_harvey/hwm_headtohead_v2.csv"
OUT_JSON = "/scratch/users/li1995/harris30m/v2_harvey/hwm_metrics.json"

FT = 0.3048
WET = 0.05
GOODQ = ("Excellent: +/- 0.05 ft", "Good: +/- 0.10 ft", "Fair: +/- 0.20 ft")

di_ds = rasterio.open(INUN); di_arr = di_ds.read(1).astype("float64")
di_arr[~np.isfinite(di_arr)] = np.nan; di_inv = ~di_ds.transform
dc_ds = rasterio.open(CRESTV1); dc_arr = dc_ds.read(1).astype("float64"); dc_inv = ~dc_ds.transform
v2_ds = rasterio.open(CRESTV2); v2_arr = v2_ds.read(1).astype("float64"); v2_inv = ~v2_ds.transform
i3_ds = rasterio.open(INUN30); i3_arr = i3_ds.read(1).astype("float64"); i3_inv = ~i3_ds.transform
fa_ds = rasterio.open(FATHOM); fa_inv = ~fa_ds.transform


def s_inun(lo, la):
    x, y = wt("EPSG:4326", di_ds.crs, [lo], [la]); c, r = di_inv * (x[0], y[0]); r, c = int(r), int(c)
    if not (0 <= r < di_ds.height and 0 <= c < di_ds.width): return None
    v = di_arr[r, c]; return 0.0 if not np.isfinite(v) else float(v)


def s_v2(lo, la):
    x, y = wt("EPSG:4326", v2_ds.crs, [lo], [la]); c, r = v2_inv * (x[0], y[0]); r, c = int(r), int(c)
    if not (0 <= r < v2_ds.height and 0 <= c < v2_ds.width): return None
    v = v2_arr[r, c]
    return None if not np.isfinite(v) else float(v)   # nan = outside county mask


def s_inun30(lo, la):
    x, y = wt("EPSG:4326", i3_ds.crs, [lo], [la]); c, r = i3_inv * (x[0], y[0]); r, c = int(r), int(c)
    if not (0 <= r < i3_ds.height and 0 <= c < i3_ds.width): return None
    v = i3_arr[r, c]
    return None if not np.isfinite(v) else float(v)   # nan = outside county mask


def s_crestv1(lo, la):
    x, y = wt("EPSG:4326", dc_ds.crs, [lo], [la]); c, r = dc_inv * (x[0], y[0]); r, c = int(r), int(c)
    if not (0 <= r < dc_ds.height and 0 <= c < dc_ds.width): return None
    v = dc_arr[r, c]; return 0.0 if v <= -9990 else float(v)


def s_fathom(lo, la):
    x, y = wt("EPSG:4326", fa_ds.crs, [lo], [la]); c, r = fa_inv * (x[0], y[0]); r, c = int(r), int(c)
    if not (0 <= r < fa_ds.height and 0 <= c < fa_ds.width): return None
    v = float(fa_ds.read(1, window=Window(c, r, 1, 1))[0, 0])
    return None if v >= 999 else v


rows = []
for r in csv.DictReader(open(HWM)):
    lo = float(r["lon"]); la = float(r["lat"])
    hag = r.get("height_above_gnd_ft")
    hag = float(hag) * FT if hag not in ("", "None", None) else np.nan
    rows.append(dict(env=r["environment"], q=r["quality"], hag=hag,
                     di=s_inun(lo, la), dc=s_crestv1(lo, la), i3=s_inun30(lo, la),
                     v2=s_v2(lo, la), fa=s_fathom(lo, la)))


def stats(rs, key):
    m = np.array([x[key] for x in rs if x[key] is not None], float)
    o = np.array([x["hag"] for x in rs if x[key] is not None], float)
    ok = np.isfinite(m) & np.isfinite(o); m, o = m[ok], o[ok]
    if m.size < 3: return None
    res = m - o
    return dict(n=int(m.size), rmse=float(np.sqrt(np.mean(res ** 2))),
                bias=float(res.mean()), mae=float(np.abs(res).mean()),
                wet=100 * float(np.mean(m > WET)))


def line(name, rs, key, sink=None, tag=None):
    s = stats(rs, key)
    if s:
        print(f"  {name:<20}: MAE {s['mae']:.2f} m  RMSE {s['rmse']:.2f} m  "
              f"bias {s['bias']:+.2f} m  wet {s['wet']:.0f}%  (n={s['n']})")
        if sink is not None: sink[tag or name] = s
    else:
        print(f"  {name:<20}: (too few)")


def sub(pred): return [x for x in rows if pred(x)]


metrics = {}
print("=" * 92)
print("HEAD-TO-HEAD @ USGS Harvey HWMs — peak model depth vs HWM height_above_gnd (m)")
print("*  = matched control pair: identical 30 m grid, DEM, Manning, MRMS, CREST layer, window, wall BC")
print("Published SOTA HWM MAE: Huang'21 0.65 | SFINCS 0.83 | CREST-iMAP 0.91 | Fathom 1.03 | Delft3D 1.34")
print("=" * 92)

# --- full-domain models: Inunda, Fathom, CREST-iMAP v2 ------------------------ #
for title, key, rs in [
    ("ALL (common coverage)", "all",
     sub(lambda x: x["fa"] is not None and x["v2"] is not None and x["i3"] is not None)),
    ("RIVERINE", "riverine",
     sub(lambda x: x["fa"] is not None and x["v2"] is not None and x["i3"] is not None and x["env"] == "Riverine")),
    ("RIVERINE, quality>=Fair", "riverine_fair",
     sub(lambda x: x["fa"] is not None and x["v2"] is not None and x["i3"] is not None
         and x["env"] == "Riverine" and x["q"] in GOODQ)),
    ("RIVERINE, hag>=0.5 m (significant)", "riverine_deep",
     sub(lambda x: x["fa"] is not None and x["v2"] is not None and x["i3"] is not None and x["env"] == "Riverine"
         and np.isfinite(x["hag"]) and x["hag"] >= 0.5)),
]:
    print(f"\n### {title}  (n={len(rs)})")
    m = metrics.setdefault(key, {})
    line("Inunda 10m", rs, "di", m, "inunda_10m")
    line("Inunda 30m *", rs, "i3", m, "inunda_30m")
    line("CREST-iMAP v2 30m *", rs, "v2", m, "crest_imap_v2_30m")
    line("Fathom 30m", rs, "fa", m, "fathom")

# --- Houston core: all four, including the published CREST-iMAP v1 grid ------- #
rs = sub(lambda x: x["dc"] is not None and x["fa"] is not None and x["i3"] is not None
         and x["v2"] is not None and x["env"] == "Riverine")
print(f"\n### 4-WAY (Houston core — CREST-iMAP v1 coverage)  (n={len(rs)})")
m = metrics.setdefault("houston_core", {})
line("Inunda 10m", rs, "di", m, "inunda_10m")
line("Inunda 30m *", rs, "i3", m, "inunda_30m")
line("CREST-iMAP v2 30m *", rs, "v2", m, "crest_imap_v2_30m")
line("CREST-iMAP v1", rs, "dc", m, "crest_imap_v1")
line("Fathom 30m", rs, "fa", m, "fathom")

os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
with open(OUT_CSV, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["environment", "quality", "hwm_depth_m", "inunda_10m_m",
                "inunda_30m_m", "crest_imap_v2_30m_m", "crest_imap_v1_m", "fathom_m"])
    for x in rows:
        w.writerow([x["env"], x["q"],
                    "" if not np.isfinite(x["hag"]) else f"{x['hag']:.3f}",
                    "" if x["di"] is None else f"{x['di']:.3f}",
                    "" if x["i3"] is None else f"{x['i3']:.3f}",
                    "" if x["v2"] is None else f"{x['v2']:.3f}",
                    "" if x["dc"] is None else f"{x['dc']:.3f}",
                    "" if x["fa"] is None else f"{x['fa']:.3f}"])
with open(OUT_JSON, "w") as f:
    json.dump(metrics, f, indent=2)
print(f"\nwrote {OUT_CSV}\nwrote {OUT_JSON}")
