"""Rasters the model cannot use must fail, not produce numbers.

  DEM     : undeclared fill values, all-nodata grids, missing or unusable
            georeferencing; declared nodata, mask-band and NaN cells are filled
  forcing : a grid with no georeferencing cannot be regridded
  io      : depth rasters say they are centimetres in their own metadata
  config  : a non-positive frame cadence is refused
"""
import datetime
import pathlib
import sys
import warnings

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
rasterio = pytest.importorskip("rasterio")
from rasterio.transform import Affine, from_origin

from crestimap import dem as demmod
from crestimap import io as iomod
from crestimap.event import EventConfig
from crestimap.forcing import SolverGrid, regrid_to_solver

ARCSEC = 1.0 / 3600.0
TR = from_origin(-97.25, 35.125, ARCSEC, ARCSEC)
Z = np.fromfunction(lambda r, c: 100 + 0.5 * c + 0.25 * r, (10, 12),
                    dtype=np.float32)


def _write(path, arr, **kw):
    kw.setdefault("crs", "EPSG:4326")
    kw.setdefault("transform", TR)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # NotGeoreferencedWarning is the point
        with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0],
                           width=arr.shape[1], count=1, dtype="float32",
                           **kw) as ds:
            ds.write(arr, 1)
    return str(path)


def _with(value):
    arr = Z.copy()
    arr[3, 3] = value
    return arr


def _from_dem(path, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return SolverGrid.from_dem(path, **kw)


def test_usable_dem_is_unchanged(tmp_path):
    g = _from_dem(_write(tmp_path / "dem.tif", Z))
    assert np.array_equal(g.z.cpu().numpy(), Z)
    assert g.transform == TR
    assert g.dx == pytest.approx(ARCSEC * 111132.0 * np.cos(np.radians(35.1236)),
                                 rel=1e-3)
    assert g.dy == pytest.approx(ARCSEC * 111132.0)


@pytest.mark.parametrize("fill", [-9999.0, -32768.0, 1e30, np.inf, -np.inf])
def test_undeclared_fill_value_is_refused(tmp_path, fill):
    with pytest.raises(ValueError, match="nodata"):
        _from_dem(_write(tmp_path / "dem.tif", _with(fill)))


def test_declared_nodata_is_filled_as_before(tmp_path):
    g = _from_dem(_write(tmp_path / "dem.tif", _with(-9999.0), nodata=-9999.0))
    assert g.z[3, 3].item() == Z.max()
    g = _from_dem(_write(tmp_path / "d2.tif", _with(-9999.0), nodata=-9999.0),
                  nodata_fill=50.0)
    assert g.z[3, 3].item() == 50.0


@pytest.mark.parametrize("tag", [None, float("nan")])
def test_nan_cells_are_filled(tmp_path, tag):
    # A NaN never compares equal to a NaN nodata tag, so these reached the solver.
    g = _from_dem(_write(tmp_path / "dem.tif", _with(np.nan), nodata=tag))
    assert np.isfinite(g.z.cpu().numpy()).all()
    assert g.z[3, 3].item() == Z.max()


def test_error_names_the_undeclared_cell_not_a_filled_one(tmp_path):
    arr = _with(1e30)
    arr[0, 0] = -9999.0
    path = _write(tmp_path / "dem.tif", arr, nodata=-9999.0)
    with pytest.raises(ValueError, match="row 3, col 3"):
        _from_dem(path)


def test_fill_value_above_any_terrain_is_refused(tmp_path):
    with pytest.raises(ValueError, match="nodata"):
        _from_dem(_write(tmp_path / "dem.tif", _with(9999.0)))


def test_mask_band_marks_cells_as_nodata(tmp_path):
    path = _write(tmp_path / "dem.tif", _with(101.5))
    mask = np.full(Z.shape, 255, dtype=np.uint8)
    mask[3, 3] = 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.open(path, "r+") as ds:
            ds.write_mask(mask)
    assert _from_dem(path).z[3, 3].item() == Z.max()


def test_all_nodata_dem_is_refused(tmp_path):
    arr = np.full_like(Z, -9999.0)
    with pytest.raises(ValueError, match="no valid"):
        _from_dem(_write(tmp_path / "dem.tif", arr, nodata=-9999.0))


def test_dem_without_georeferencing_is_refused(tmp_path):
    path = tmp_path / "dem.tif"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.open(path, "w", driver="GTiff", height=10, width=12,
                           count=1, dtype="float32") as ds:
            ds.write(Z, 1)
    with pytest.raises(ValueError, match="georeferenc"):
        _from_dem(str(path))


def test_metric_coordinates_without_crs_are_refused(tmp_path):
    # Read as degrees, 25 m pixels would become 2,778 km cells.
    path = _write(tmp_path / "dem.tif", Z, crs=None,
                  transform=from_origin(500000.0, 4000000.0, 25.0, 25.0))
    with pytest.raises(ValueError, match="CRS"):
        _from_dem(path)


def test_metric_coordinates_under_a_geographic_label_are_refused():
    # String CRSs reach the geographic branch too: dx would be hundreds of km.
    tr = from_origin(500000.0, 4000000.0, 25.0, 25.0)
    for crs in ("EPSG:32614", rasterio.crs.CRS.from_epsg(4326)):
        with pytest.raises(ValueError, match="CRS"):
            SolverGrid.from_array(Z, tr, crs)


def test_projected_dem_uses_native_cell_size(tmp_path):
    path = _write(tmp_path / "dem.tif", Z, crs="EPSG:32614",
                  transform=from_origin(500000.0, 4000000.0, 25.0, 30.0))
    g = _from_dem(path)
    assert (g.dx, g.dy) == (25.0, 30.0)


def test_lonlat_coordinates_without_crs_are_still_geographic(tmp_path):
    g = _from_dem(_write(tmp_path / "dem.tif", Z, crs=None))
    assert g.dy == pytest.approx(ARCSEC * 111132.0)


def test_rotated_dem_is_refused(tmp_path):
    tr = Affine(ARCSEC, ARCSEC / 2, -97.0, ARCSEC / 2, -ARCSEC, 35.0)
    with pytest.raises(ValueError, match="rotated"):
        _from_dem(_write(tmp_path / "dem.tif", Z, transform=tr))


@pytest.mark.parametrize("bad", [
    Affine(0.0, 0.0, -97.0, 0.0, -ARCSEC, 35.0),
    Affine(float("nan"), 0.0, -97.0, 0.0, -ARCSEC, 35.0),
    Affine(float("inf"), 0.0, -97.0, 0.0, -ARCSEC, 35.0),
])
def test_from_array_refuses_bad_pixel_size(bad):
    with pytest.raises(ValueError, match="pixel size"):
        SolverGrid.from_array(Z, bad, "EPSG:4326")


def test_from_array_refuses_non_terrain():
    for arr in (np.full_like(Z, np.nan), _with(-9999.0), _with(np.nan)):
        with pytest.raises(ValueError, match="nodata"):
            SolverGrid.from_array(arr, TR, None)


def _load_dem_from_tile(tmp_path, monkeypatch, arr):
    tile = _write(tmp_path / "tile.tif", arr, crs="EPSG:4269", nodata=-999999.0)
    monkeypatch.setattr(demmod, "fetch_tile", lambda *a, **k: tile)
    w, n = TR.c, TR.f
    bbox = (w, n - 10 * ARCSEC, w + 12 * ARCSEC, n)
    z, tr, crs = demmod.load_dem(bbox, cache_dir=str(tmp_path))
    return SolverGrid.from_array(z, tr, crs)


def test_3dep_path_passes_and_fills_declared_nodata(tmp_path, monkeypatch):
    g = _load_dem_from_tile(tmp_path, monkeypatch, _with(-999999.0))
    assert np.isfinite(g.z.cpu().numpy()).all()
    assert g.z[3, 3].item() == pytest.approx(np.delete(Z.ravel(), 3 * 12 + 3).min())
    assert g.dy == pytest.approx(ARCSEC * 111132.0)


def test_3dep_path_refuses_all_nodata_domain(tmp_path, monkeypatch):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # nanmin of an empty slice
        with pytest.raises(ValueError, match="nodata"):
            _load_dem_from_tile(tmp_path, monkeypatch,
                                np.full_like(Z, -999999.0))


def test_regrid_refuses_grid_without_georeferencing():
    with pytest.raises(ValueError, match="georeferenc"):
        regrid_to_solver(np.ones((4, 4)), Affine.identity(), (3, 3), TR)


def test_depth_raster_declares_its_scale_and_units(tmp_path):
    path = str(tmp_path / "depth.tif")
    depth = np.array([[0.0, 1.0], [2.5, 655.35]])
    iomod.write_depth(path, depth, TR, "EPSG:4326")
    with rasterio.open(path) as ds:
        assert ds.dtypes[0] == "uint16"
        assert ds.scales == (0.01,)
        assert ds.units == ("m",)
        assert ds.read(1)[0, 1] == 100
    back, _, _ = iomod.read_depth(path)
    assert np.allclose(back, depth)


@pytest.mark.parametrize("every", [0.0, -900.0])
def test_nonpositive_frame_cadence_is_refused(every):
    # Used to spin forever advancing the next-frame time by nothing.
    t0 = datetime.datetime(2026, 8, 10)
    with pytest.raises(ValueError, match="output_every_s"):
        EventConfig(event_id="e", bbox=(0, 0, 1, 1), t0=t0, t_end=t0,
                    ef5_output_dir=".", out_dir=".", output_every_s=every)
