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
import os
import warnings
warnings.simplefilter("ignore")


# OBS= np.loadtxt('/home/ZhiLi/CRESTHH/data/streamGauge/08068500.txt', delimiter=' ', usecols=(2,4,6), 
                # converters= {2: })
OBS= pd.read_csv('/home/ZhiLi/CRESTHH/data/streamGauge/08068500.txt', delimiter='\t',
                 names=['USGS','ID','date','TZ','Q',' ','H',' '], converters={'date':pd.to_datetime}).set_index('date')
OBS.index= OBS.index.tz_localize('US/Central').tz_convert('UTC').tz_localize(None)
GAUGE_LOC= (-94.4359, 30.1109)


def RMSE(obs, sim):
    '''Compute the RMSE of two time series data'''
    return np.nanmean((obs-sim)**2)**.5

def single_thread(*params):
    
    global OBS, GAUGE_LOC, myid
    start='20170401050000'
    end=  '20170402000000'
    interval= '1H'
    yieldstep= pd.Timedelta(interval).total_seconds()    
    params= params[0]
    myProj= Proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    topo_file= '/home/ZhiLi/CRESTHH/data/Example-cali/DEM_filled.tif'    
    if myid==0:
        shp= gpd.read_file('/home/ZhiLi/CRESTHH/data/Example-cali/watershed_shp/watershed.shp')

        lons= np.array(shp.exterior[1].coords)[:,0]; lats=np.array(shp.exterior[1].coords)[:,1]
        
        utm_coords= [myProj(lon,lat) for (lon, lat) in zip(lons, lats)]
        
        DOMAIN= anuga.create_domain_from_regions(
                utm_coords,
                boundary_tags={'bottom': [0]},
                maximum_triangle_area=1000000)
        DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
        DOMAIN.set_quantity('elevation', filename=topo_file, location='centroids') # Use function for elevation
        DOMAIN.set_quantity('friction',  filename='/home/ZhiLi/CRESTHH/data/Texas_friction/manningn.tif', location='centroids')                        # Constant friction 
        DOMAIN.set_quantity('stage', expression='elevation + 10', location='centroids')  
        Br = anuga.Reflective_boundary(DOMAIN)
        Bt = anuga.Transmissive_boundary(DOMAIN)        
        DOMAIN.set_boundary({'bottom':   Bt,
                            'exterior': Br})
    else:
        DOMAIN=None
    barrier()
    DOMAIN= distribute(DOMAIN)
    DOMAIN.set_name('temp')
    DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
  
    DOMAIN.set_quantity('SS0', 0, location='centroids')
    DOMAIN.set_quantity('SI0', 0, location='centroids')
    DOMAIN.set_quantity('W0', 0, location='centroids')    
    DOMAIN.set_quantity('RainFact', params[0], location='centroids')
    DOMAIN.set_quantity('Ksat', filename='/hydros/MengyuChen/ef5_param/crest_params/ksat_usa.tif', location='centroids')
    DOMAIN.quantities['Ksat'].centroid_values[:]*= params[1]
    DOMAIN.set_quantity('WM', filename='/hydros/MengyuChen/ef5_param/crest_params/wm_usa.tif', location='centroids')
    DOMAIN.quantities['WM'].centroid_values[:]*= params[2]
    DOMAIN.set_quantity('B', filename='/hydros/MengyuChen/ef5_param/crest_params/b_usa.tif', location='centroids')
    DOMAIN.quantities['B'].centroid_values[:]*= params[3]
    DOMAIN.set_quantity('IM', filename='/hydros/MengyuChen/ef5_param/crest_params/im_usa.tif', location='centroids')
    DOMAIN.quantities['IM'].centroid_values[:]*= params[4]
    DOMAIN.set_quantity('KE', params[5], location='centroids')
    DOMAIN.set_quantity('coeM', params[6], location='centroids')
    DOMAIN.set_quantity('expM', params[7], location='centroids')
    DOMAIN.set_quantity('coeR', params[8], location='centroids')
    DOMAIN.set_quantity('coeS', params[9], location='centroids')
    DOMAIN.set_quantity('KS', params[10], location='centroids')
    DOMAIN.set_quantity('KI', params[11], location='centroids')
    DOMAIN.set_evap_dir('/home/ZhiLi/CRESTHH/data/evap', pattern='cov_et17%m%d.asc.tif', freq='1D')
    DOMAIN.set_precip_dir('/hydros/MengyuChen/mrmsPrecRate',
            pattern='PrecipRate_00.00_%Y%m%d-%H%M00.grib2-var0-z0.tif', freq=interval)
    DOMAIN.set_timestamp(start, format='%Y%m%d%H%M%S')
    DOMAIN.set_time_interval(interval)
    total_seconds= (pd.to_datetime(end) - pd.to_datetime(start)).total_seconds()


    for t in DOMAIN.evolve(yieldstep=yieldstep, duration=total_seconds):
        if myid==0:
            DOMAIN.print_timestepping_statistics()

    DOMAIN.sww_merge(verbose=False)
    if myid==0:
        swwfile = '/home/ZhiLi/CRESTHH/Examples/calibration/temp.sww'
        os.system('rm temp_P*')
        splotter = anuga.SWW_plotter(swwfile)
        stage= splotter.stage
        speed= splotter.speed
        # collocate gauge point
        to_utm_y, to_utm_x= myProj(GAUGE_LOC[0], GAUGE_LOC[1])
        xc = splotter.xc + splotter.xllcorner
        yc = splotter.yc + splotter.yllcorner
        iloc= np.argmin( (xc-to_utm_x)**2 + (yc-to_utm_y)**2 )
        sim= stage[:,iloc]
        sim_v= speed[:,iloc]
        obs= OBS.resample('1H', label='right').mean().loc[pd.date_range(start,
                        end, freq=interval),['H','Q']]
        
        np.save('%s.npy'%params[-1], params)
        df= pd.DataFrame(index= pd.date_range(start,
                        end, freq=interval))
        df['Stage_sim']= sim
        df['Stage_obs']= obs.H.values*0.3048
        df['Velocity_sim']= sim_v
        df['Q_obs']= obs.Q.values
        df.to_csv('%s.csv'%(str(params[-1])))
        loss= RMSE(obs.H.values*0.3048, sim) 
        
        print 'LOSS: ', loss
    
        return loss
    else:
        pass

def evaluate(values):

    Y= []
    prev_loss= np.inf
    for i in range(len(values)):
        args= np.append(values[i,:],int(i))
        loss= single_thread(args)
        if loss<prev_loss and myid==0:
            os.system('mv temp.sww best.sww')
            os.system('rm temp.sww')

        Y.append(loss)

    return Y

# Global variables
# SHP= gpd.read_file('watershed_shp/watershed.shp')
# TOPO_FILE = 'DEM_filled.tif'
# lons= np.array(SHP.exterior[1].coords)[:,0]; lats=np.array(SHP.exterior[1].coords)[:,1]
# myProj = Proj("+proj=utm +zone=15, +south +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
# utm_coords= [myProj(lon,lat) for (lon, lat) in zip(lons, lats)]
# DOMAIN= anuga.create_domain_from_regions(
#             utm_coords,
#             boundary_tags={'bottom': [0]},
#             maximum_triangle_area=1000000)

# # Config model domain
# DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
# DOMAIN.set_quantity('elevation', filename=topography_file, location='centroids') # Use function for elevation
# DOMAIN.set_quantity('friction', 0.03, location='centroids')                        # Constant friction 
# DOMAIN.set_quantity('stage', expression='elevation', location='centroids')         # Dry Bed 
# DOMAIN.set_quantity('SS0', 0, location='centroids')
# DOMAIN.set_quantity('SI0', 0, location='centroids')
# DOMAIN.set_quantity('W0', 0, location='centroids')
# # DOMAIN.set_quantity('RainFact', 0.5, location='centroids')
# # DOMAIN.set_quantity('Ksat', 0.5, location='centroids')
# # DOMAIN.set_quantity('WM', 0.5, location='centroids')
# # DOMAIN.set_quantity('B', 0.5, location='centroids')
# # DOMAIN.set_quantity('IM', 0.5, location='centroids')
# # DOMAIN.set_quantity('KE', 0.5, location='centroids')
# # DOMAIN.set_quantity('coeM', 0.5, location='centroids')
# # DOMAIN.set_quantity('expM', 0.5, location='centroids')
# # DOMAIN.set_quantity('coeR', 0.5, location='centroids')
# # DOMAIN.set_quantity('coeS', 0.5, location='centroids')
# # DOMAIN.set_quantity('KS', 0.5, location='centroids')
# # DOMAIN.set_quantity('KI', 0.5, location='centroids')
# DOMAIN.set_evap_dir('/home/ZhiLi/CRESTHH/data/evap', pattern='cov_et17%m%d.asc.tif', freq='1D')
# DOMAIN.set_precip_dir('/hydros/MengyuChen/mrmsPrecRate',pattern='PrecipRate_00.00_%Y%m%d-%H%M00.grib2-var0-z0.tif', freq='2M')
# DOMAIN.set_timestamp('20170825180000', format='%Y%m%d%H%M%S')
# DOMAIN.set_time_interval('1H')
# # Boundary condition
# Br = anuga.Reflective_boundary(domain)
# Bt = anuga.Transmissive_boundary(domain)

# DOMAIN.set_boundary({'bottom':   Bt,
#                      'exterior': Br})

# Parameters to calibrate:
#RainFact, Ksat, WM, B, IM, KE, coeM, coeR, coeS, KS, KI (lumped)

# def evaluate(obs, **params):

#     '''
#     Args:
#     --------------------------
#     obs   - np.array object: time series of dependent value
#     paras - dict,
#             'RainFact': float,
#             'Ksat': float,
#             'WM': float,
#             'B': float,
#             'IM': float,
#             'KE': float,
#             'coeM': float,
#             'expM': float,
#             'coeR': float,
#             'coeS': float,
#             'KS': float,
#             'KI': float,
#             'simu_name': str

#     Returns:
#     --------------------------
#     simu - np.array object: simulation by CRESTHH
#     obs  - np.array object: observation by validation source
#     loss - float: the objective value
#     '''

#     global DOMAIN
#     DOMAIN.set_name(params['simu_name'])
#     DOMAIN.set_quantity('RainFact', params['RainFact'], location='centroids')
#     DOMAIN.set_quantity('Ksat', params['Ksat'], location='centroids')
#     DOMAIN.set_quantity('WM', params['WM'], location='centroids')
#     DOMAIN.set_quantity('B', params['B'], location='centroids')
#     DOMAIN.set_quantity('IM', params['IM'], location='centroids')
#     DOMAIN.set_quantity('KE', params['KE'], location='centroids')
#     DOMAIN.set_quantity('coeM', params['coeM'], location='centroids')
#     DOMAIN.set_quantity('expM', params['expM'], location='centroids')
#     DOMAIN.set_quantity('coeR', params['coeR'], location='centroids')
#     DOMAIN.set_quantity('coeS', params['coeS'], location='centroids')
#     DOMAIN.set_quantity('KS', params['KS'], location='centroids')
#     DOMAIN.set_quantity('KI', params['KI'], location='centroids')

#     for t in DOMAIN.evolve(yieldstep=20, duration=300):
#         DOMAIN.print_timestepping_statistics()

#     # open .sww file
#     swwfile = params['simu_name']
#     splotter = anuga.SWW_plotter(swwfile)
#     depth= splotter.depth

#     loss= RMSE(obs, sim)
    
#     return loss

