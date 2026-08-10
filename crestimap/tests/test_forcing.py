"""EF5 coupling tests: filename parsing, 3" -> 1/3" regrid mass conservation,
hourly hold behavior, and end-to-end volume balance through the solver.

CREST-AI's EF5 writes runoff/subrunoff grids at 3 arc-seconds (~90 m);
the solver runs on the 1/3 arc-second (~10 m) DEM grid — a 9x9 nesting.
"""
import datetime
import math
import pathlib
import sys
import tempfile

import numpy as np
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from crestimap import SWESolver
from crestimap.forcing import (GriddedSeriesForcing, SolverGrid, ef5_forcing,
                               parse_ef5_dir, regrid_to_solver)

torch.set_default_dtype(torch.float64)

rasterio = None
try:
    import rasterio
    from rasterio.transform import from_origin
except ImportError:
    pass

SEC3 = 1.0 / 1200.0          # 3 arc-seconds in degrees
SEC13 = SEC3 / 9.0           # 1/3 arc-second
W, N = -97.5, 35.4           # domain upper-left (OK-ish latitude)
NYC, NXC = 6, 8              # coarse EF5 grid
NYF, NXF = NYC * 9, NXC * 9  # fine solver grid, exactly nested
T0 = datetime.datetime(2026, 8, 10, 0, 0)


def _write_ef5_outputs(d):
    rng = np.random.default_rng(7)
    tr = from_origin(W, N, SEC3, SEC3)
    grids = {}
    for kind, scale in (("runoff", 12.0), ("subrunoff", 2.0)):
        grids[kind] = []
        for hh in range(3):
            arr = (scale * rng.random((NYC, NXC))).astype(np.float32)
            arr[0, 0] = -9999.0  # nodata cell
            t = T0 + datetime.timedelta(hours=hh)
            # EF5's real filename format (YYYYMMDD_HHUU); hour 0 uses the
            # underscore-less variant so both spellings stay covered
            ts = f"{t:%Y%m%d%H%M}" if hh == 0 else f"{t:%Y%m%d_%H%M}"
            p = str(d / f"{kind}.{ts}.crest.tif")
            with rasterio.open(p, "w", driver="GTiff", height=NYC, width=NXC,
                               count=1, dtype="float32", crs="EPSG:4326",
                               transform=tr, nodata=-9999.0) as ds:
                ds.write(arr, 1)
            grids[kind].append(arr)
    # decoy from another model + an unrelated file
    (d / "runoff.202608100000.hp.tif").write_bytes(b"")
    (d / "ts.crest.csv").write_bytes(b"")
    return grids


def _fine_grid(d):
    tr = from_origin(W, N, SEC13, SEC13)
    z = np.zeros((NYF, NXF), dtype=np.float32)
    p = str(d / "dem.tif")
    with rasterio.open(p, "w", driver="GTiff", height=NYF, width=NXF, count=1,
                       dtype="float32", crs="EPSG:4326", transform=tr) as ds:
        ds.write(z, 1)
    return SolverGrid.from_dem(p)


def test_parse_and_model_filter(tmp=None):
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        _write_ef5_outputs(d)
        s = parse_ef5_dir(d, "runoff", model="crest")
        assert len(s) == 3 and s[0][0] == T0 and s[-1][0] - s[0][0] == \
            datetime.timedelta(hours=2)
        assert len(parse_ef5_dir(d, "runoff")) == 4  # includes hp decoy


def test_containing_cell_mass_conservation():
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        grids = _write_ef5_outputs(d)
        grid = _fine_grid(d)
        # metric cell sizes: fine should be coarse/9
        assert abs(grid.dx * 9 - SEC3 * 111132.0 *
                   math.cos(math.radians(N - SEC3 * NYC / 2))) / (grid.dx * 9) < 1e-3
        fn = ef5_forcing(d, grid, T0, model="crest")
        for hh in range(3):
            fine = fn(hh * 3600.0 + 1800.0).numpy()  # mid-hour -> that hour's grid
            coarse = sum(np.clip(np.where(g[hh] == -9999.0, 0.0, g[hh]),
                                 0, None).astype(np.float64)
                         for g in grids.values())
            # exact nesting: mean over each 9x9 block == coarse rate (mm/h -> m/s)
            blocks = fine.reshape(NYC, 9, NXC, 9).mean(axis=(1, 3))
            ref = coarse / 3600.0 / 1000.0
            assert np.abs(blocks - ref).max() < 1e-15
            # total mass: rate is intensive, equal-area nesting -> sums match
            assert abs(fine.mean() - ref.mean()) / ref.mean() < 1e-12


def test_hold_vs_interp():
    times = [T0, T0 + datetime.timedelta(hours=1)]
    mk = lambda v: np.full((2, 2), v)
    hold = GriddedSeriesForcing(times, lambda i: mk([10.0, 20.0][i]), T0, hold=True)
    lin = GriddedSeriesForcing(times, lambda i: mk([10.0, 20.0][i]), T0, hold=False)
    m = 1 / 3600.0 / 1000.0
    assert abs(hold(1800.0).mean().item() - 10.0 * m) < 1e-18
    assert abs(lin(1800.0).mean().item() - 15.0 * m) < 1e-18
    assert abs(hold(-5.0).mean().item() - 10.0 * m) < 1e-18   # clamps to first
    assert abs(hold(7200.0).mean().item() - 20.0 * m) < 1e-18  # holds last


def test_end_to_end_volume():
    """Closed flat basin + EF5 forcing: solver volume gain == forced volume."""
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        _write_ef5_outputs(d)
        grid = _fine_grid(d)
        fn = ef5_forcing(d, grid, T0, model="crest")
        s = SWESolver(grid.z, dx=grid.dx, dy=grid.dy, order=2, bc="wall")
        h = torch.full_like(grid.z, 0.05)
        t_end = 2 * 3600.0
        h2, _, _ = s.run(h.clone(), torch.zeros_like(h), torch.zeros_like(h),
                         t_end=t_end, rain_fn=fn)
        gained = (h2 - h).sum().item() * grid.dx * grid.dy
        expect = sum(fn(hh * 3600.0 + 1.0).sum().item() * 3600.0
                     for hh in range(2)) * grid.dx * grid.dy
        assert abs(gained - expect) / expect < 1e-9, (gained, expect)


if __name__ == "__main__":
    if rasterio is None:
        print("SKIP: rasterio not available")
        sys.exit(0)
    for fn in (test_parse_and_model_filter, test_containing_cell_mass_conservation,
               test_hold_vs_interp, test_end_to_end_volume):
        fn()
        print(f"PASS  {fn.__name__}")
    print("all forcing tests passed")
