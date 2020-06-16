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
start='20170401000000'
end=  '20170901000000'
interval= '2M'
if myid==0:

    
    yieldstep= pd.Timedelta(interval).total_seconds()    
    topo_file= '/home/ZhiLi/CRESTHH/Examples/excessive_rain/68500_sub/subDEM_filled.tif'
    study_area= gpd.read_file('/home/ZhiLi/CRESTHH/Examples/excessive_rain/68500_sub/68500_basin.shp')
    interior_area= gpd.read_file('/home/ZhiLi/CRESTHH/Examples/excessive_rain/68500_sub/68500_river_buffer_cliped.shp')
    base_resolution = 1000000 #1km
    interior_resolution= 1000 #10 m2    
    # study_area= gpd.read_file('watershed_shp/watershed.shp')
    
    myProj = Proj("+proj=utm +zone=15, +south +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    
    lons= np.array(study_area.exterior[0].coords)[:,0]; lats=np.array(study_area.exterior[0].coords)[:,1]
    utm_coords_ext= [myProj(lon,lat) for (lon, lat) in zip(lons, lats)]
    lons= np.array(interior_area.exterior[4].coords)[:,0]; lats=np.array(interior_area.exterior[4].coords)[:,1]
    utm_coords_int= [myProj(lon,lat) for (lon, lat) in zip(lons, lats)]    
    if os.path.exists('1km_082500.msh'):
        DOMAIN= anuga.create_domain_from_file('1km_082500.msh')
    else:
        DOMAIN= anuga.create_domain_from_regions(
            utm_coords_ext,
            boundary_tags={'bottom': [0]},
            maximum_triangle_area=1000000,
            # interior_regions=[[utm_coords_int, interior_resolution]],
            mesh_filename='1km_082500.msh')    
    # domain= anuga.create_domain_from_regions(bounding_polygon, boundary_tags={'bottom':[0],}, maximum_triangle_area=0.001,verbose=True)
    DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    DOMAIN.set_quantity('elevation', filename=topo_file, location='centroids') # Use function for elevation
    DOMAIN.set_quantity('friction',  filename='/home/ZhiLi/CRESTHH/data/Texas_friction/manningn.tif', location='centroids')                        # Constant friction 
    DOMAIN.set_quantity('stage', expression='elevation', location='centroids')  
    DOMAIN.set_quantity('SM', 0.012, location='centroids')
    DOMAIN.set_quantity('Ksat', filename='/hydros/MengyuChen/ef5_param/crest_params/ksat_usa.tif', location='centroids')
    DOMAIN.quantities['Ksat'].centroid_values[:]*= 289.0
    DOMAIN.set_quantity('WM', filename='/hydros/MengyuChen/ef5_param/crest_params/wm_usa.tif', location='centroids')
    DOMAIN.quantities['WM'].centroid_values[:]*= 871.0
    DOMAIN.set_quantity('B', filename='/hydros/MengyuChen/ef5_param/crest_params/b_usa.tif', location='centroids')
    DOMAIN.quantities['B'].centroid_values[:]*= 5e-10
    DOMAIN.set_quantity('IM', filename='/hydros/MengyuChen/ef5_param/crest_params/im_usa.tif', location='centroids')
    DOMAIN.quantities['IM'].centroid_values[:]*= 0.06
    DOMAIN.set_quantity('KE', 0.415853, location='centroids')
    Br = anuga.Reflective_boundary(DOMAIN)
    Bt = anuga.Transmissive_boundary(DOMAIN)
    Bi = anuga.Dirichlet_boundary([0, 0, 0]) 

    DOMAIN.set_boundary({'bottom':   Bt,
                        'exterior': Br})
else:
    DOMAIN=None

barrier()

DOMAIN= distribute(DOMAIN)
DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")

#domain.set_evap_dir('/hydros/MengyuChen/pet', pattern='cov_et17%m%d.asc', freq='D')
#domain.set_precip_dir('/home/ZhiLi/CRESTHH/data/precip',pattern='imerg%Y%m%dS%H%M%S.tif', freq='H')
#domain.set_timestamp('20170825180000', format='%Y%m%d%H%M%S')
#domain.set_time_interval('1H')

DOMAIN.set_evap_dir('/home/ZhiLi/CRESTHH/data/evap', pattern='cov_et17%m%d.asc.tif', freq='1D')
# domain.set_precip_dir('/home/ZhiLi/CRESTHH/data/precip',pattern='nimerg%Y%m%dS%H%M%S.tif', freq='H')
DOMAIN.set_precip_dir('/hydros/MengyuChen/mrmsPrecRate',pattern='PrecipRate_00.00_%Y%m%d-%H%M00.grib2-var0-z0.tif', freq=interval)
DOMAIN.set_timestamp(start, format='%Y%m%d%H%M%S')
DOMAIN.set_time_interval(interval)
total_seconds= (pd.to_datetime(end) - pd.to_datetime(start)).total_seconds()


for t in DOMAIN.evolve(yieldstep=120, duration=total_seconds):
    if myid==0:
        DOMAIN.write_time()

DOMAIN.sww_merge(verbose=True)

if myid==0:
    OBS= pd.read_csv('/home/ZhiLi/CRESTHH/data/streamGauge/08068500.txt', delimiter='\t',
                 names=['USGS','ID','date','TZ','Q',' ','H',' '], converters={'date':pd.to_datetime}).set_index('date')
    OBS.index= OBS.index.tz_localize('US/Central').tz_convert('UTC').tz_localize(None)
    splotter = anuga.SWW_plotter(swwfile)
    stage= splotter.stage
    speed= splotter.speed
    exc_rain= splotter.exc_rain
    SM= splotter.SM
    # collocate gauge point
    proj= "+proj=utm +zone=15, +south +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
    wgs84= CRS('EPSG:4326')
    UTM= CRS(proj)
    GAUGE_LOC= (-95.43666, 30.11085)
    to_utm_x, to_utm_y= transform(UTM,wgs84,GAUGE_LOC[0], GAUGE_LOC[1])
    xc = splotter.xc + splotter.xllcorner
    yc = splotter.yc + splotter.yllcorner    
    iloc= np.argmin( (xc-to_utm_x)**2 + (yc-to_utm_y)**2 )
    obs= OBS.resample('1H', label='right').mean().loc[pd.date_range(start,
                    end, freq=interval),['H','Q']]
    df= pd.DataFrame(index= pd.date_range(start,
                        end, freq=interval))
    df['Stage_sim_68500']= stage[:,iloc]
    df['Stage_obs_68500']= obs.H.values*0.3048
    df['Velocity_sim_68500']= speed[:,iloc]
    df['Q_obs_68500']= obs.Q.values
    df['excessive_rain_68500']= exc_rain[:,iloc]
    df['SM_68500']= SM[:,iloc]
    OBS= pd.read_csv('/home/ZhiLi/CRESTHH/data/streamGauge/08068275.txt', delimiter='\t',
                 names=['USGS','ID','date','TZ','Q',' ','H',' '], converters={'date':pd.to_datetime}).set_index('date')
    OBS.index= OBS.index.tz_localize('US/Central').tz_convert('UTC').tz_localize(None)    
    obs= OBS.resample('1H', label='right').mean().loc[pd.date_range(start,
                    end, freq=interval),['H','Q']]    
    GAUGE_LOC= (-95.646063,30.11935)
    to_utm_x, to_utm_y= transform(UTM,wgs84,GAUGE_LOC[0], GAUGE_LOC[1])
    iloc= np.argmin( (xc-to_utm_x)**2 + (yc-to_utm_y)**2 )
    df['Stage_sim_68275']= stage[:,iloc]
    df['Stage_obs_68275']= obs.H.values*0.304
    df['Velocity_sim_68275']= speed[:,iloc]
    df['Q_obs_68275']= obs.Q.values
    df['excessive_rain_68275']= exc_rain[:,iloc]
    df['SM_68275']= SM[:,iloc]
    df.to_csv('results.csv')