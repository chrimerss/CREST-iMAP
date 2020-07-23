import sys
sys.path.append('/home/ZhiLi/CRESTHH')
import cresthh
from cresthh import anuga
from cresthh import UQ
from cresthh.UQ.optimization import SCE
from cresthh import metrics as met
from cresthh.UQ.DoE import morris_oat
from cresthh.UQ.test_functions import Sobol_G
from cresthh.UQ.util import scale_samples_general, read_param_file, discrepancy
from cresthh.utils import processSWW
from cresthh.utils import flowAreaCalc as flow_area
import geopandas as gpd
import shutil
import numpy as np
import model
import os 
import pandas as pd

def RMSE(obs, sim):
    '''Compute the RMSE of two time series data'''
    return np.nanmean((obs-sim)**2)**.5

# Read in parameter file
param_file = 'params.txt'
pf= read_param_file(param_file)

param_values= morris_oat.sample(30, pf['num_vars'], num_levels=10, grid_jump=1, plot=False)
scale_samples_general(param_values, pf['bounds'])

np.savetxt('Input_params.txt', param_values, delimiter=' ')

# shutil.copy('model.py', '/home/ZhiLi/CRESTHH/cresthh/UQ/test_functions/functn.py')
Y= []
for i, params in enumerate(param_values):
    print params
    os.system('mpirun -n 40 python model.py %f %f %f %f %f %f %f > anuga.log'%(params[0],params[1],params[2],
                                                                    params[3],params[4],params[5],params[6]))
    # os.system('mpirun -n 40 python model.py %f > anuga.log'%params)
    swwfile = 'temp.sww'
    os.system('rm temp_P*')
    
    OUTLET= (296751.22158,3292640.32167)
    # xc= splotter.xc +splotter.xllcorner
    # yc= splotter.yc +splotter.yllcorner
    # iloc= np.argmin((xc-OUTLET[0])**2+ (yc-OUTLET[1])**2)
    # stage= splotter.stage[:,iloc]
    # speed= splotter.speed[:,iloc]
    # stage_b= benchmark.stage[:,iloc]
    # speed_b= benchmark.speed[:,iloc]
    crossSection= gpd.read_file('/home/ZhiLi/CRESTHH/data/crosssection/crosssection.shp')
    sim= processSWW('temp.sww', ['depth','speed','stage'], OUTLET, start_time=pd.to_datetime('20170825000000'))
    benchmark= processSWW('Coupled_10m_modified_mesh.sww', ['depth','speed','stage'], OUTLET, start_time=pd.to_datetime('20170825000000'))
    sim['area']= sim.apply(lambda x: flow_area(crossSection, x.stage), axis=1)
    benchmark['area']= benchmark.apply(lambda x: flow_area(crossSection, x.stage), axis=1)   
    sim['Q']= sim.speed * sim.area
    benchmark['Q']= benchmark.speed * benchmark.area     
    loss= RMSE(benchmark.Q, sim.Q)
    nash= met.nse(benchmark.Q, sim.Q)
    time_peak= met.peak_time_error(benchmark.Q, sim.Q).seconds
    peak_flow= met.peak_flow_error(benchmark.Q, sim.Q)
    rb= met.rb(benchmark.Q, sim.Q)
    print '%d/%d loss: %f'%(i,len(param_values),loss)
    # Y.append(loss)
    with open('Output_Sobol.txt', 'a') as f:
        f.write('%f,%f,%f,%f,%f\n'%(loss, nash, time_peak, peak_flow, rb))

# np.savetxt('Output_Sobol.txt', np.array(Y), delimiter=' ')


# def 