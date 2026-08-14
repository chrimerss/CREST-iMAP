"""P1.6 EventSession gates on synthetic data (no network, no EF5).

Gate 1  session-continuation equivalence: three successive bundle visits vs
        one continuous solve of the same span — wet Jaccard >= 0.99, mean
        wet |Δdepth| < 2 cm at the final time.
Gate 2  interleave: two events' sessions alternating visits produce exactly
        what each produces alone (no cross-contamination of state).
Gate 4  restart recovery: a fresh session resumed from the published
        junction frame (init_depth, momentum at rest) continues within the
        gate-1 tolerance of the unbroken session.

Gate 3 (GPU-minutes per catch-up visit at ~4.7 M cells) is measured on the
HPC and reported in docs/P1_6_VALIDATION.md.
"""
import datetime
import os
import pathlib
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from crestimap import EventConfig
from crestimap.io import read_depth
from crestimap.session import EventSession

DEVICE = os.environ.get("CRESTIMAP_TEST_DEVICE", "cpu")

rasterio = None
try:
    import rasterio
    from rasterio.transform import from_origin
except ImportError:
    pass

SEC3 = 1.0 / 1200.0
W, N = -97.5, 35.4
NYC, NXC = 12, 16
T0 = datetime.datetime(2026, 8, 10, 12, 0)
H = datetime.timedelta(hours=1)


def _synthetic_dir(d, seed=3, channel_row=None, hours=8):
    """Valley DEM + EF5 q/runoff/subrunoff grids covering T0-2h .. T0+(hours-3)h."""
    ny, nx = NYC * 3, NXC * 3
    tr = from_origin(W, N, SEC3 / 3, SEC3 / 3)
    yy, xx = np.mgrid[0:ny, 0:nx]
    z = (0.002 * xx * 30.0
         + 0.5 * np.abs(yy - ny / 2) / (ny / 2) * 8.0)
    dem_path = str(d / "dem_in.tif")
    with rasterio.open(dem_path, "w", driver="GTiff", height=ny, width=nx,
                       count=1, dtype="float32", crs="EPSG:4326",
                       transform=tr) as ds:
        ds.write(z.astype(np.float32), 1)
    tre = from_origin(W, N, SEC3, SEC3)
    rng = np.random.default_rng(seed)
    row = channel_row if channel_row is not None else NYC // 2
    for hh in range(hours):
        t = T0 + datetime.timedelta(hours=hh - 2)
        for kind, base in (("runoff", 25.0), ("subrunoff", 4.0)):
            arr = (base * (0.5 + rng.random((NYC, NXC)))).astype(np.float32)
            with rasterio.open(str(d / f"{kind}.{t:%Y%m%d%H%M}.crest.tif"),
                               "w", driver="GTiff", height=NYC, width=NXC,
                               count=1, dtype="float32", crs="EPSG:4326",
                               transform=tre) as ds:
                ds.write(arr, 1)
        q = np.zeros((NYC, NXC), dtype=np.float32)
        q[row, :] = 40.0
        with rasterio.open(str(d / f"q.{t:%Y%m%d%H%M}.crest.tif"), "w",
                           driver="GTiff", height=NYC, width=NXC, count=1,
                           dtype="float32", crs="EPSG:4326",
                           transform=tre) as ds:
            ds.write(q, 1)
    return dem_path


def _cfg(d, dem_path, out, t0=T0, t_end=None):
    return EventConfig(
        event_id="sess_test", bbox=(W, N - NYC * SEC3, W + NXC * SEC3, N),
        t0=t0, t_end=t_end or (t0 + 2 * H), ef5_output_dir=str(d),
        out_dir=str(out), model="crest", sim_start=T0 - H,
        dem_path=dem_path, output_every_s=900.0, device=DEVICE)


def _final_frame(out_dir, manifest):
    depth, _, _ = read_depth(os.path.join(out_dir, manifest["frames"][-1]["file"]))
    return depth


def _gate1(a, b, label):
    wet_a, wet_b = a > 0.02, b > 0.02
    inter = np.logical_and(wet_a, wet_b).sum()
    union = np.logical_or(wet_a, wet_b).sum()
    jac = inter / union if union else 1.0
    wet = np.logical_or(wet_a, wet_b)
    mad = float(np.abs(a - b)[wet].mean()) if wet.any() else 0.0
    print(f"  {label}: wet Jaccard {jac:.4f}, mean wet |dz| {mad * 100:.2f} cm")
    assert jac >= 0.99, f"{label}: Jaccard {jac:.4f} < 0.99"
    assert mad < 0.02, f"{label}: mean wet |dz| {mad * 100:.2f} cm >= 2 cm"


def test_gate1_continuation_equivalence():
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        dem = _synthetic_dir(d)
        # three successive bundles: t0 = T0, T0+1h, T0+2h (horizon 2 h each)
        s = EventSession(_cfg(d, dem, d / "o1"), resume=False)
        s.advance(str(d), str(d / "o1"), T0, T0 + 2 * H, device=DEVICE)
        assert s.state_time() == T0, "held state must sit at the junction"
        s.advance(str(d), str(d / "o2"), T0 + H, T0 + 3 * H, device=DEVICE)
        assert s.state_time() == T0 + H
        m3 = s.advance(str(d), str(d / "o3"), T0 + 2 * H, T0 + 4 * H,
                       device=DEVICE)
        assert m3["sim_start"] == (T0 + H).strftime("%Y-%m-%dT%H:%MZ")
        # continuous reference: one visit over the whole span
        r = EventSession(_cfg(d, dem, d / "ref"), resume=False)
        mr = r.advance(str(d), str(d / "ref"), T0 + 2 * H, T0 + 4 * H,
                       device=DEVICE)
        _gate1(_final_frame(str(d / "o3"), m3),
               _final_frame(str(d / "ref"), mr), "gate1 3-bundle vs continuous")
        # record contiguity: the merged record (carry-forward keeps frames
        # strictly before each visit's sim_start; each visit re-emits its
        # junction frame) has no gap wider than 2 frame intervals
        merged = {}
        for o, start in (("o1", T0 - H), ("o2", T0), ("o3", T0 + H)):
            for f in os.listdir(str(d / o)):
                if f.startswith("depth_") and f.endswith(".tif"):
                    t = datetime.datetime.strptime(f[6:-4], "%Y%m%d%H%M")
                    if t >= start:            # what this visit publishes
                        merged[t] = o
        times = sorted(merged)
        assert times[0] == T0 - H and times[-1] >= T0 + 4 * H - \
            datetime.timedelta(seconds=60), f"span {times[0]}..{times[-1]}"
        gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
        assert max(gaps) <= 1800 + 60, \
            f"gap {max(gaps):.0f} s in the merged frame record"


def test_gate2_interleave_isolation():
    with tempfile.TemporaryDirectory() as ta, \
            tempfile.TemporaryDirectory() as tb:
        da, db = pathlib.Path(ta), pathlib.Path(tb)
        dem_a = _synthetic_dir(da, seed=3, channel_row=NYC // 2)
        dem_b = _synthetic_dir(db, seed=11, channel_row=NYC // 3)
        # interleaved: A1 B1 A2 B2
        sa = EventSession(_cfg(da, dem_a, da / "a1"), resume=False)
        sb = EventSession(_cfg(db, dem_b, db / "b1"), resume=False)
        sa.advance(str(da), str(da / "a1"), T0, T0 + 2 * H, device=DEVICE)
        sb.advance(str(db), str(db / "b1"), T0, T0 + 2 * H, device=DEVICE)
        ma = sa.advance(str(da), str(da / "a2"), T0 + H, T0 + 3 * H,
                        device=DEVICE)
        mb = sb.advance(str(db), str(db / "b2"), T0 + H, T0 + 3 * H,
                        device=DEVICE)
        # solo runs of each
        s2 = EventSession(_cfg(da, dem_a, da / "s1"), resume=False)
        s2.advance(str(da), str(da / "s1"), T0, T0 + 2 * H, device=DEVICE)
        ma_solo = s2.advance(str(da), str(da / "s2"), T0 + H, T0 + 3 * H,
                             device=DEVICE)
        s3 = EventSession(_cfg(db, dem_b, db / "t1"), resume=False)
        s3.advance(str(db), str(db / "t1"), T0, T0 + 2 * H, device=DEVICE)
        mb_solo = s3.advance(str(db), str(db / "t2"), T0 + H, T0 + 3 * H,
                             device=DEVICE)
        a_i = _final_frame(str(da / "a2"), ma)
        a_s = _final_frame(str(da / "s2"), ma_solo)
        b_i = _final_frame(str(db / "b2"), mb)
        b_s = _final_frame(str(db / "t2"), mb_solo)
        assert np.array_equal(a_i, a_s), "event A contaminated by interleave"
        assert np.array_equal(b_i, b_s), "event B contaminated by interleave"
        assert not np.array_equal(a_i, b_i), \
            "A and B identical — fixture not discriminating"
        print("  gate2: interleaved == solo, bit-exact, for both events")


def test_gate4_restart_recovery():
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        dem = _synthetic_dir(d)
        # unbroken session through two visits
        s = EventSession(_cfg(d, dem, d / "v1"), resume=False)
        s.advance(str(d), str(d / "v1"), T0, T0 + 2 * H, device=DEVICE)
        m2 = s.advance(str(d), str(d / "v2"), T0 + H, T0 + 3 * H,
                       device=DEVICE)
        # restart: rebuild from the published junction frame (visit 2 opens
        # holding at T0 — its first frame IS the junction state at T0)
        d2 = pathlib.Path(str(d) + "_rs")
        shutil.copytree(str(d), str(d2))
        shutil.copy(str(d / "v1" / f"depth_{T0:%Y%m%d%H%M}.tif"),
                    str(d2 / f"init_depth_{T0:%Y%m%d%H%M}.tif"))
        s2 = EventSession(_cfg(d2, dem, d2 / "v2"), resume=True)
        assert s2.state_time() == T0, "resume did not land on the junction"
        m2r = s2.advance(str(d2), str(d2 / "v2"), T0 + H, T0 + 3 * H,
                         device=DEVICE)
        _gate1(_final_frame(str(d / "v2"), m2),
               _final_frame(str(d2 / "v2"), m2r), "gate4 restart vs unbroken")


if __name__ == "__main__":
    if rasterio is None:
        print("SKIP: rasterio not available")
        sys.exit(0)
    for fn in (test_gate1_continuation_equivalence,
               test_gate2_interleave_isolation,
               test_gate4_restart_recovery):
        fn()
        print(f"PASS  {fn.__name__}")
    print("all session gates passed")
