import numpy as num
# from print_stats import print_test_stats, build_full_flag
# import cresthh.anuga
import sys
sys.path.append('/home/ZhiLi/CRESTHH')
import cresthh.anuga
from cresthh import anuga
from cresthh.anuga import Domain
import pandas as pd
# from anuga import Transmissive_boundary, Refelective_boundary

from cresthh.anuga import distribute, myid, numprocs, finalize, barrier
import geopandas as gpd
from pyproj import Proj, CRS, transform

topography_file= 'DEM_filled.tif'
if myid==0:
    # xleft= -95.05
    # xright=-95.83
    # ybottom=29.79
    # ytop=30.18

    # point_sw = [xleft, ybottom]
    # point_se = [xright, ybottom]
    # point_nw = [xleft, ytop]    
    # point_ne = [xright, ytop]

    # bounding_polygon = [point_se,
    #                 point_ne,
    #                 point_nw,
    #                 point_sw]
    # bounding_polygon= gpd.read_file('area/domain.shp')
    bounding_polygon= gpd.read_file('watershed_shp/watershed.shp')
    lons= num.array(bounding_polygon.exterior[1].coords)[:,0]; lats=num.array(bounding_polygon.exterior[1].coords)[:,1]
    myProj = Proj("+proj=utm +zone=15, +south +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    utm_coords= [myProj(lon,lat) for (lon, lat) in zip(lons, lats)]
    # domain= anuga.create_domain_from_regions(bounding_polygon, boundary_tags={'bottom':[0],}, maximum_triangle_area=0.001,verbose=True)
    domain = cresthh.anuga.create_domain_from_regions(
                utm_coords,
                boundary_tags={'bottom': [0]},
                maximum_triangle_area=1000000,
                )

    domain.set_name('excessive_rain_para')    
    domain.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    domain.set_quantity('elevation', filename=topography_file, location='centroids') # Use function for elevation
    domain.set_quantity('friction', 0.3, location='centroids')                        # Constant friction 
    domain.set_quantity('stage', expression='elevation', location='centroids')         # Dry Bed 

    domain.set_quantity('SS0', 0, location='centroids')
    domain.set_quantity('SI0', 0, location='centroids')
    domain.set_quantity('W0', 0, location='centroids')
    domain.set_quantity('RainFact', 0.5, location='centroids')
    domain.set_quantity('Ksat', 0.5, location='centroids')
    domain.set_quantity('WM', 0.5, location='centroids')
    domain.set_quantity('B', 0.5, location='centroids')
    domain.set_quantity('IM', 0.5, location='centroids')
    domain.set_quantity('KE', 0.5, location='centroids')
    domain.set_quantity('coeM', 0.5, location='centroids')
    domain.set_quantity('expM', 0.5, location='centroids')
    domain.set_quantity('coeR', 0.5, location='centroids')
    domain.set_quantity('coeS', 0.5, location='centroids')
    domain.set_quantity('KS', 0.5, location='centroids')
    domain.set_quantity('KI', 0.5, location='centroids')

    Br = anuga.Reflective_boundary(domain)
    Bt = anuga.Transmissive_boundary(domain)
    Bi = anuga.Dirichlet_boundary([0, 0, 0]) 

    domain.set_boundary({'bottom':   Bt,
                        'exterior': Bi})
else:
    domain=None

barrier()

domain= distribute(domain)
domain.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")

#domain.set_evap_dir('/hydros/MengyuChen/pet', pattern='cov_et17%m%d.asc', freq='D')
#domain.set_precip_dir('/home/ZhiLi/CRESTHH/data/precip',pattern='imerg%Y%m%dS%H%M%S.tif', freq='H')
#domain.set_timestamp('20170825180000', format='%Y%m%d%H%M%S')
#domain.set_time_interval('1H')

domain.set_evap_dir('/home/ZhiLi/CRESTHH/data/evap', pattern='cov_et17%m%d.asc.tif', freq='1D')
# domain.set_precip_dir('/home/ZhiLi/CRESTHH/data/precip',pattern='nimerg%Y%m%dS%H%M%S.tif', freq='H')
domain.set_precip_dir('/hydros/MengyuChen/mrmsPrecRate',pattern='PrecipRate_00.00_%Y%m%d-%H%M00.grib2-var0-z0.tif', freq='1H')
domain.set_timestamp('20170826050000', format='%Y%m%d%H%M%S')
domain.set_time_interval('1H')
total_seconds= (pd.to_datetime('20170901000000') - pd.to_datetime('20170826050000')).total_seconds()


for t in domain.evolve(yieldstep=3600, duration=total_seconds):
    if myid==0:
        domain.write_time()

domain.sww_merge(verbose=True)
