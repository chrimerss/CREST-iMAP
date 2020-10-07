import click
import logging
import sys

from terraincache import TerrainTiles
from rasterio.rio import options
from cligj import verbose_opt, quiet_opt


LOG = logging.getLogger(__name__)


@click.command("terraincache")
@click.option(
    "--out_file",
    "--out-file",
    "-o",
    default="terrain-tiles.tif",
    type=click.Path(resolve_path=True),
    help="Output file name/path",
)
@click.option(
    "--bounds",
    callback=options.bounds_handler,
    required=True,
    help='Bounds: "left bottom right top" or "[left, bottom, right, top]".',
)
@click.option("--zoom", "-z", type=int, required=True, help="Web map zoom level")
@click.option(
    "--cache-dir",
    "--cache_dir",
    "-p",
    envvar="TERRAINCACHE",
    help="Path to cache folder",
)
@click.option(
    "-tr",
    "--target_resolution",
    type=float,
    default=25,
    help="Output dataset target resolution in meters (square pixels)",
)
@click.option(
    "--bounds-crs", "--bounds_crs", help="CRS of provided bounds", default="EPSG:4326"
)
@click.option(
    "--dst-crs",
    "--dst_crs",
    default="EPSG:3005",
    help="Target coordinate reference system.",
)
@click.option(
    "-r",
    "--resampling_algorithm",
    type=click.Choice(
        ["bilinear", "nearest", "cubic", "cubicspline", "lanczos", "average", "mode"],
        case_sensitive=False,
    ),
    default="bilinear",
    help="GDAL resampling algorithm",
)
@verbose_opt
@quiet_opt
def cli(
    out_file,
    bounds,
    zoom,
    cache_dir,
    target_resolution,
    bounds_crs,
    dst_crs,
    resampling_algorithm,
    verbose,
    quiet,
):
    """Write terrain tiles to geotiff"""
    verbosity = verbose - quiet
    log_level = max(10, 30 - 10 * verbosity)
    logging.basicConfig(stream=sys.stderr, level=log_level)
    LOG.info(bounds)
    tt = TerrainTiles(
        bounds,
        zoom,
        bounds_crs=bounds_crs,
        cache_dir=cache_dir,
        resolution=target_resolution,
        dst_crs=dst_crs,
    )
    tt.save(out_file)


if __name__ == "__main__":
    cli()
