import pandas as pd
import sys
sys.path.append('/home/ZhiLi/CRESTHH')
# sys.path.append('/home/ZhiLi/CRESTHH/data/Example-cali')
import cresthh
import cresthh.anuga as anuga
from cresthh.anuga import Domain
from osgeo import gdal
from glob import glob
from affine import Affine
import geopandas as gpd
from pyproj import Proj, CRS, transform
import numpy as np
from cresthh.anuga import distribute, myid, numprocs, finalize, barrier


def compute(*params):
    global OBS, GAUGE_LOC, myid
    start='20170401050000'
    end='20170901000000'
    params= params[0]
    if myid==0:
        shp= gpd.read_file('/home/ZhiLi/CRESTHH/data/Example-cali/watershed_shp/watershed.shp')
        topo_file= '/home/ZhiLi/CRESTHH/data/Example-cali/DEM_filled.tif'
        lons= np.array(shp.exterior[1].coords)[:,0]; lats=np.array(shp.exterior[1].coords)[:,1]
        myProj= Proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
        utm_coords= [myProj(lon,lat) for (lon, lat) in zip(lons, lats)]
        
        DOMAIN= anuga.create_domain_from_regions(
                utm_coords,
                boundary_tags={'bottom': [0]},
                maximum_triangle_area=1000000)

        DOMAIN.set_name('temp')
        DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
        DOMAIN.set_quantity('elevation', filename=topo_file, location='centroids') # Use function for elevation
        DOMAIN.set_quantity('friction',  filename='/home/ZhiLi/CRESTHH/data/Texas_friction/manningn.tif', location='centroids')                        # Constant friction 
        DOMAIN.set_quantity('stage', expression='elevation + 10', location='centroids')         
        DOMAIN.set_quantity('SS0', 0, location='centroids')
        DOMAIN.set_quantity('SI0', 0, location='centroids')
        DOMAIN.set_quantity('W0', 0, location='centroids')
        DOMAIN.set_quantity('RainFact', params[0], location='centroids')
        DOMAIN.set_quantity('Ksat', params[1], location='centroids')
        DOMAIN.set_quantity('WM', params[2], location='centroids')
        DOMAIN.set_quantity('B', params[3], location='centroids')
        DOMAIN.set_quantity('IM', params[4], location='centroids')
        DOMAIN.set_quantity('KE', params[5], location='centroids')
        DOMAIN.set_quantity('coeM', params[6], location='centroids')
        DOMAIN.set_quantity('expM', params[7], location='centroids')
        DOMAIN.set_quantity('coeR', params[8], location='centroids')
        DOMAIN.set_quantity('coeS', params[9], location='centroids')
        DOMAIN.set_quantity('KS', params[10], location='centroids')
        DOMAIN.set_quantity('KI', params[11], location='centroids')
        Br = anuga.Reflective_boundary(DOMAIN)
        Bt = anuga.Transmissive_boundary(DOMAIN)

        DOMAIN.set_boundary({'bottom':   Bt,
                            'exterior': Br})
    else:
        DOMAIN=None
        
    barrier()
    DOMAIN= distribute(DOMAIN)

    DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    DOMAIN.set_evap_dir('/home/ZhiLi/CRESTHH/data/evap', pattern='cov_et17%m%d.asc.tif', freq='1D')
    DOMAIN.set_precip_dir('/hydros/MengyuChen/mrmsPrecRate',pattern='PrecipRate_00.00_%Y%m%d-%H%M00.grib2-var0-z0.tif', freq='1H')
    DOMAIN.set_timestamp(start, format='%Y%m%d%H%M%S')
    DOMAIN.set_time_interval('1H')
    total_seconds= (pd.to_datetime(end) - pd.to_datetime(start)).total_seconds()


    for t in DOMAIN.evolve(yieldstep=3600, duration=total_seconds):
        DOMAIN.print_timestepping_statistics()

    DOMAIN.sww_merge(verbose=False)
    


if __name__=='__main__':
    import argparse
    parser= argparse.ArgumentParser(description='Input parameters for calibration')
    parser.add_argument('--params', type=float, nargs='+',
                    help='Rainfact, Ksat, WM, B, IM, KE, coeM, expM, coeR, coeS, KS, KI')
    args= parser.parse_args()

    compute(args.params)