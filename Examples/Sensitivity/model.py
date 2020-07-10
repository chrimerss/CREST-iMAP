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
import argparse
from pyproj import Proj, CRS, transform
import numpy as np
from cresthh.anuga import distribute, myid, numprocs, finalize, barrier
import os
import warnings
warnings.simplefilter("ignore")


if __name__=='__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('params', nargs='+', type=str)
    params= parser.parse_args().params[0]
    params= params.split(' ')
    params= [float(param) for param in params]

    global myid
    start='20170825000000'
    end=  '20170826000000'
    interval= '2M'
    yieldstep= pd.Timedelta(interval).total_seconds()    
    params= params[0]
    
    topo_file='/hydros/ZhiLi/DEM_10m_filled.tif'
    # study_area= gpd.read_file('/home/ZhiLi/CRESTHH/Examples/excessive_rain/68500_sub/68500_basin.shp')
    # interior_area= gpd.read_file('/home/ZhiLi/CRESTHH/Examples/excessive_rain/68500_sub/68500_river_buffer_cliped.shp')
    # base_resolution = 1000000 #1km
    # interior_resolution= 1000 #10 m2    
    if myid==0:
        # shp= gpd.read_file('/home/ZhiLi/CRESTHH/data/Example-cali/watershed_shp/watershed.shp')


        DOMAIN= anuga.create_domain_from_file('/home/ZhiLi/mesher/examples/Houston/stream_dem/DEM_10m.mesh')
        # if os.path.exists('1km.msh'):
        #     DOMAIN= anuga.create_domain_from_file('1km.msh')
        # else:
        #     DOMAIN= anuga.create_domain_from_regions(
        #         utm_coords,
        #         boundary_tags={'bottom': [0]},
        #         maximum_triangle_area=1000000,
        #         interior_regions=[[utm_coords_int, interior_resolution]],
        #         mesh_filename='1km_082500.msh')
        DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
        DOMAIN.set_quantity('elevation', filename=topo_file, location='centroids') # Use function for elevation
        DOMAIN.set_quantity('friction',  filename='/home/ZhiLi/CRESTHH/data/Texas_friction/manningn.tif', location='centroids')
                                # Constant friction 
        DOMAIN.set_quantity('stage', expression='elevation', location='centroids')  
        
        DOMAIN.set_quantity('Ksat', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/ksat.tif', location='centroids')
        
        DOMAIN.set_quantity('WM', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/wm_10m.tif', location='centroids')
        
        DOMAIN.set_quantity('B', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/b_10m.tif', location='centroids')
        
        DOMAIN.set_quantity('IM', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/im.tif', location='centroids')
        
        Br = anuga.Reflective_boundary(DOMAIN)
        Bt = anuga.Transmissive_boundary(DOMAIN)        
        DOMAIN.set_boundary({'bottom':   Bt,
                            'interior': Br,
                            'exterior': Br})
    else:
        DOMAIN=None
    barrier()
    DOMAIN= distribute(DOMAIN)
    DOMAIN.set_name('temp')
    DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    DOMAIN.quantities['friction'].centroid_values[:]*= params
    # DOMAIN.set_quantity('SM', params[1], location='centroids')
    # DOMAIN.quantities['Ksat'].centroid_values[:]*= params[2]
    # DOMAIN.quantities['WM'].centroid_values[:]*= params[3]
    # DOMAIN.quantities['B'].centroid_values[:]*= params[4]
    # DOMAIN.quantities['IM'].centroid_values[:]*= params[5]
    # DOMAIN.set_quantity('KE', params[6], location='centroids')



    DOMAIN.set_evap_dir('/home/ZhiLi/CRESTHH/data/evap', pattern='cov_et17%m%d.asc.tif', freq='1D')
    DOMAIN.set_precip_dir('/home/ZhiLi/CRESTHH/data/synthetic_rainfall',pattern='PrecipRate_00.00_%Y%m%d-%H%M00.grib2-var0-z0.tif', freq=interval)
    DOMAIN.set_timestamp(start, format='%Y%m%d%H%M%S')
    DOMAIN.set_time_interval(interval)
    DOMAIN.set_coupled(True)
    total_seconds= (pd.to_datetime(end) - pd.to_datetime(start)).total_seconds()


    for t in DOMAIN.evolve(yieldstep=yieldstep, duration=total_seconds):
        if myid==0:
            DOMAIN.print_timestepping_statistics()
            print 'friction:', DOMAIN.get_quantity('friction').centroid_values[50]
            pass

    DOMAIN.sww_merge(verbose=False)
    # finalize()
    # if myid==0:
    #     swwfile = 'temp.sww'
    #     os.system('rm temp_P*')
    #     splotter = anuga.SWW_plotter(swwfile)
    #     benchmark= anuga.SWW_plotter('Coupled_10m_modified_mesh.sww')
        
    #     OUTLET= (296090.4,3291818.4)
    #     xc= splotter.xc +splotter.xllcorner
    #     yc= splotter.yc +splotter.yllcorner
    #     iloc= np.argmin((xc-OUTLET[0])**2+ (yc-OUTLET[1])**2)
    #     stage= splotter.stage[:,iloc]
    #     speed= splotter.speed[:,iloc]
    #     stage_b= benchmark.stage[:,iloc]
    #     speed_b= benchmark.speed[:,iloc]
    #     print stage.sum(), speed.sum(), stage_b.sum(), speed_b.sum()
    #     loss= RMSE(stage*speed, stage_b*speed_b)

    #     return loss
    # else:
    #     pass

# def evaluate(values):
    
#     Y= []
#     prev_loss= np.inf
#     for i in range(len(values)):
#             loss= single_thread(values[i,:])
#             print '%d/%d, loss: %.2f'%(i,len(values),loss)
#             os.system('rm temp.sww')

#             Y.append(loss)
#     if myid==0:
#         return Y

