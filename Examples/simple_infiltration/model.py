'''A simplified Green-Ampt infiltration model from Wells, Larry G.; Ward, A. D.; Moore, I. D.; and Phillips, R. E., "Comparison of Four Infiltration Models in Characterizing Infiltration
Through Surface Mine Profiles" (1986). Biosystems and Agricultural Engineering Faculty Publications. 184.
https://uknowledge.uky.edu/bae_facpub/184'''

import numpy as num
import sys
sys.path.append('/home/ZhiLi/CRESTHH')
import cresthh.anuga
from cresthh import anuga
from cresthh.anuga import Domain
import pandas as pd
import numpy as np
import os

from cresthh.anuga import distribute, myid, numprocs, finalize, barrier
import geopandas as gpd
from pyproj import Proj, CRS, transform
import time

start_time= time.time()
myProj= Proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
start='20170825120000'
end=  '20170831000000'
interval= '2M'
if myid==0:

    
    yieldstep= pd.Timedelta(interval).total_seconds()    
    topo_file= '/hydros/ZhiLi/demHouston033s_NAm83fel.tif'
    # topo_file='/hydros/ZhiLi/DEM_10m_filled.tif'
    # topo_file= '/home/ZhiLi/mesher/examples/flow_accumulation/flow_accumulation/DEM_10m/DEM_10m_projected.tif'
    # DOMAIN= anuga.create_domain_from_file('/home/ZhiLi/mesher/examples/08076700_new/stream_dem/DEM_10m.mesh')
    DOMAIN= anuga.create_domain_from_file('/home/ZhiLi/CRESTHH/Examples/Sensitivity/original_08076700.msh')
    DOMAIN.set_name('coupled_orig_mesh')
    DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    DOMAIN.set_quantity('elevation', filename=topo_file, location='centroids') # Use function for elevation
    DOMAIN.set_quantity('friction',  filename='/home/ZhiLi/CRESTHH/data/Texas_friction/manningn.tif', location='centroids')                        # Constant friction 
    DOMAIN.set_quantity('stage', expression='elevation', location='centroids')  
    # DOMAIN.set_quantity('SM', 0.039, location='centroids')
    DOMAIN.set_quantity('Ksat', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/ksat.tif', location='centroids')
    # DOMAIN.quantities['Ksat'].centroid_values[:]*= 289.0
    DOMAIN.set_quantity('WM', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/wm_10m.tif', location='centroids')
    # DOMAIN.quantities['WM'].centroid_values[:]*= 871.0
    DOMAIN.set_quantity('B', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/b_10m.tif', location='centroids')
    # DOMAIN.quantities['B'].centroid_values[:]*= 5e-10
    DOMAIN.set_quantity('IM', filename='/hydros/MengyuChen/Summer/New/CREST_parameters/crest_param/im.tif', location='centroids')
    # DOMAIN.quantities['IM'].centroid_values[:]*= 0.06
    DOMAIN.set_quantity('KE', 1, location='centroids')
    
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
#0.057 0.889 0.579 2.715 2.604
DOMAIN.quantities['stage'].centroid_values[:]+= 0.057
DOMAIN.quantities['friction'].centroid_values[:]*= 0.889
DOMAIN.set_quantity('SM', 0.579, location='centroids')
# DOMAIN.quantities['Ksat'].centroid_values[:]*= 2.715
# DOMAIN.quantities['WM'].centroid_values[:]*= params[3]
DOMAIN.quantities['B'].centroid_values[:]*= 2.715
DOMAIN.quantities['IM'].centroid_values[:]*= 2.604
DOMAIN.set_proj("+proj=utm +zone=15, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
DOMAIN.set_coupled(True)
DOMAIN.set_infiltration(False)


DOMAIN.set_evap_dir('/home/ZhiLi/CRESTHH/data/evap', pattern='cov_et17%m%d.asc.tif', freq='1D')
# domain.set_precip_dir('/home/ZhiLi/CRESTHH/data/precip',pattern='nimerg%Y%m%dS%H%M%S.tif', freq='H')
DOMAIN.set_precip_dir('/hydros/MengyuChen/mrmsPrecRate',pattern='PrecipRate_00.00_%Y%m%d-%H%M00.grib2-var0-z0.tif', freq=interval)
DOMAIN.set_timestamp(start, format='%Y%m%d%H%M%S')
DOMAIN.set_time_interval(interval)
total_seconds= (pd.to_datetime(end) - pd.to_datetime(start)).total_seconds()


for t in DOMAIN.evolve(yieldstep=60*15, duration=total_seconds):
    if myid==0:
        DOMAIN.write_time()

DOMAIN.sww_merge(verbose=True)
end_time= time.time()
print 'Simulation costs %.2f hours'%((end_time-start_time)/3600.)