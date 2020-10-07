import os
from pathlib import Path
import logging
import tempfile
import subprocess

from osgeo import gdal
import mercantile
import rasterio
from rasterio.warp import transform_bounds

import requests


LOG = logging.getLogger(__name__)


class TerrainTiles(object):
    def __init__(
        self,
        bounds,
        zoom=11,
        bounds_crs="EPSG:4326",
        dst_crs="EPSG:4326",
        resolution=None,
        cache_dir=None,
        resampling="bilinear",
    ):

        # create a temp folder for vrts
        self.tempfolder = tempfile.mkdtemp(prefix="terrain-tiles-")

        # zoom must be 1-15
        if type(zoom) != int or zoom < 1 or zoom > 15:
            raise ValueError("Zoom must be an integer from 1-15")

        # if cache is not specified
        if not cache_dir:
            # first look for environment variable
            if "TERRAINCACHE" in os.environ.keys():
                cache_dir = os.environ["TERRAINCACHE"]
            # then default to temp folder
            else:
                cache_dir = self.tempfolder

        self.cache_dir = cache_dir
        self.zoom = zoom
        self.bounds = bounds
        if bounds_crs != "EPSG:4326":
            self.bounds_ll = transform_bounds(bounds_crs, "EPSG:4326", *bounds)
        else:
            self.bounds_ll = bounds
        self.bounds_crs = bounds_crs

        self.url = "http://s3.amazonaws.com/elevation-tiles-prod/geotiff/"
        self.tiles = [t for t in mercantile.tiles(*self.bounds_ll, self.zoom)]
        self.files = []
        self.merged = False
        self.warped = False
        self.resolution = resolution
        self.dst_crs = dst_crs
        self.resampling = resampling
        self.cache()

    def download_tile(self, tile):
        """Download a terrain tile to cache, where tile is a Mercantile Tile
        """
        tilepath = "/".join([str(tile.z), str(tile.x), str(tile.y) + ".tif"])
        LOG.debug(f"Downloading tile {tilepath} to cache")
        cachepath = Path(self.cache_dir).joinpath(tilepath)
        cachepath.parent.mkdir(parents=True, exist_ok=True)
        url = self.url + tilepath
        r = requests.get(url, stream=True)
        if r.status_code != 200:
            raise RuntimeError("No such tile: {}".format(tilepath))
        with cachepath.open("wb") as fd:
            for chunk in r.iter_content(chunk_size=128):
                fd.write(chunk)
        self.files.append(str(cachepath))

    def cache(self):
        """Find geotiffs that intersect provided bounds in cache or on web
        """
        for tile in self.tiles:
            tilepath = "/".join([str(tile.z), str(tile.x), str(tile.y) + ".tif"])
            cachepath = Path(self.cache_dir).joinpath(tilepath)
            if cachepath.exists():
                LOG.debug(f"Found tile {tilepath} in cache")
                self.files.append(str(cachepath))
            else:
                self.download_tile(tile)

    def merge(self, out_file=None):
        """
        Create virtual merge of individual terrain tiles at given zoom, bounds

        Merging with rasterio.merge may run up on system limits, just use gdal.
        https://github.com/mapbox/rasterio/issues/1636
        https://github.com/smnorris/terraincache/issues/2
        """
        self.merged = os.path.join(self.tempfolder, "merge.vrt")
        vrt_options = gdal.BuildVRTOptions(resampleAlg=self.resampling)
        gdal.BuildVRT(self.merged, self.files, options=vrt_options)
        if out_file:
            LOG.info(f"writing {out_file}")
            cmd = ["gdal_translate", "-ot", "Int16", self.merged, out_file]
            subprocess.run(cmd)
            self.merged = out_file

    def warp(self, out_file=None):
        """reproject, resample, convert to int16
        """
        if not out_file:
            out_file = os.path.join(str(self.tempfolder), "warped.vrt")
        if self.bounds_crs != self.dst_crs:
            target_extent = transform_bounds(
                self.bounds_crs, self.dst_crs, *self.bounds
            )
            te = [str(t) for t in target_extent]
        else:
            te = [str(t) for t in self.bounds]
        cmd = [
            "gdalwarp",
            "-t_srs",
            self.dst_crs,
            "-te",
            te[0],
            te[1],
            te[2],
            te[3],
            "-r",
            self.resampling,
            "-ot",
            "Int16",
            "-dstnodata",
            "-32768",
            self.merged,
            out_file,
        ]
        if self.resolution:
            cmd.extend(["-tr", str(self.resolution), str(self.resolution)])
        LOG.debug(" ".join(cmd))
        subprocess.run(cmd)
        self.warped = str(out_file)

    def load(self):
        """read merged, warped raster and return np array
        """
        if not self.merged:
            self.merge()
        if not self.warped:
            self.warp()
        with rasterio.open(self.warped) as src:
            array = src.read(1)
        return array

    def save(self, out_file):
        """save merged and warped raster to specified path
        """
        if not self.merged:
            self.merge()
        self.warp(out_file)
        self.out_file = out_file
