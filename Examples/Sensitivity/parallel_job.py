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
import numpy as np
import os

from cresthh.anuga import distribute, myid, numprocs, finalize, barrier
import geopandas as gpd
from pyproj import Proj, CRS, transform


myProj= Proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
start='20170825000000'
end=  '20170826000000'
interval= '2M'
if myid==0:

    
    yieldstep= pd.Timedelta(interval).total_seconds()    
    # topo_file= '/hydros/ZhiLi/demHouston033s_NAm83fel.tif'
    topo_file='/hydros/ZhiLi/DEM_100m_Harris_fill.tif'
    # study_area= gpd.read_file('/home/ZhiLi/CRESTHH/Examples/excessive_rain/68500_sub/68500_basin.shp')
    # interior_area= gpd.read_file('/home/ZhiLi/CRESTHH/data/buffered_mainstream_new/mainstream_buffer.shp')
    # base_resolution = 1000000 #1km
    # interior_resolution= 1000 #10 m2    
    
    # myProj = Proj("+proj=utm +zone=15, +south +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    
    # lons= np.array(study_area.exterior[0].coords)[:,0]; lats=np.array(study_area.exterior[0].coords)[:,1]
    # utm_coords_ext= [myProj(lon,lat) for (lon, lat) in zip(lons, lats)]
    # lons= np.array(interior_area.exterior[0].coords)[:,0]; lats=np.array(interior_area.exterior[0].coords)[:,1]
    # utm_coords_int= [myProj(lon,lat) for (lon, lat) in zip(lons, lats)]    
    # if os.path.exists('1km_082500.msh'):
    DOMAIN= anuga.create_domain_from_file('/home/ZhiLi/mesher/examples/Harris/stream_dem/DEM_10m.mesh')
    # DOMAIN= anuga.create_domain_from_file('1km_Houston_house_removed.msh')
    # else:
    #     DOMAIN= anuga.create_domain_from_regions(
    #         utm_coords_ext,
    #         boundary_tags={'bottom': [0]},
    #         maximum_triangle_area=1000000,
    #         interior_regions=[[utm_coords_int, interior_resolution]],
    #         mesh_filename='1km_082500.msh')    
    # domain= anuga.create_domain_from_regions(bounding_polygon, boundary_tags={'bottom':[0],}, maximum_triangle_area=0.001,verbose=True)
    DOMAIN.set_name('Coupled_100m_modified_mesh')
    DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    DOMAIN.set_quantity('elevation', filename=topo_file, location='centroids') # Use function for elevation
    DOMAIN.set_quantity('friction',  filename='/home/ZhiLi/CRESTHH/data/Texas_friction/manningn.tif', location='centroids')                        # Constant friction 
    DOMAIN.set_quantity('stage', expression='elevation', location='centroids')  
    DOMAIN.set_quantity('SM', 0, location='centroids')
    DOMAIN.set_quantity('Ksat', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/ksat.tif', location='centroids')
    # DOMAIN.quantities['Ksat'].centroid_values[:]*= 289.0
    DOMAIN.set_quantity('WM', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/wm_10m.tif', location='centroids')
    # DOMAIN.quantities['WM'].centroid_values[:]*= 871.0
    DOMAIN.set_quantity('B', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/b_10m.tif', location='centroids')
    # DOMAIN.quantities['B'].centroid_values[:]*= 5e-10
    DOMAIN.set_quantity('IM', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/im.tif', location='centroids')
    # DOMAIN.quantities['IM'].centroid_values[:]*= 0.06
    DOMAIN.set_quantity('KE', 0.415853, location='centroids')
    
    Br = anuga.Reflective_boundary(DOMAIN)
    Bt = anuga.Transmissive_boundary(DOMAIN)
    Bi = anuga.Dirichlet_boundary([0, 0, 0]) 

    DOMAIN.set_boundary({'bottom':   Bt,
                        'interior': Br,
                        'exterior': Br})
else:
    DOMAIN=None

barrier()

DOMAIN= distribute(DOMAIN)
DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
DOMAIN.set_coupled(True)

#domain.set_evap_dir('/hydros/MengyuChen/pet', pattern='cov_et17%m%d.asc', freq='D')
#domain.set_precip_dir('/home/ZhiLi/CRESTHH/data/precip',pattern='imerg%Y%m%dS%H%M%S.tif', freq='H')
#domain.set_timestamp('20170825180000', format='%Y%m%d%H%M%S')
#domain.set_time_interval('1H')

DOMAIN.set_evap_dir('/home/ZhiLi/CRESTHH/data/evap', pattern='cov_et17%m%d.asc.tif', freq='1D')
# domain.set_precip_dir('/home/ZhiLi/CRESTHH/data/precip',pattern='nimerg%Y%m%dS%H%M%S.tif', freq='H')
DOMAIN.set_precip_dir('/home/ZhiLi/CRESTHH/data/synthetic_rainfall',pattern='PrecipRate_00.00_%Y%m%d-%H%M00.grib2-var0-z0.tif', freq=interval)
DOMAIN.set_timestamp(start, format='%Y%m%d%H%M%S')
DOMAIN.set_time_interval(interval)
total_seconds= (pd.to_datetime(end) - pd.to_datetime(start)).total_seconds()


for t in DOMAIN.evolve(yieldstep=120, duration=total_seconds):
    if myid==0:
        DOMAIN.write_time()

DOMAIN.sww_merge(verbose=True)
