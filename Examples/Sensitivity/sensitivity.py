import sys
sys.path.append('/home/ZhiLi/CRESTHH')
import cresthh
from cresthh import anuga
from cresthh import UQ
from cresthh.UQ.optimization import SCE

from cresthh.UQ.DoE import morris_oat
from cresthh.UQ.test_functions import Sobol_G
from cresthh.UQ.util import scale_samples_general, read_param_file, discrepancy
import shutil
import numpy as np
import model
import os 

def RMSE(obs, sim):
    '''Compute the RMSE of two time series data'''
    return np.nanmean((obs-sim)**2)**.5

# Read in parameter file
param_file = 'params.txt'
pf= read_param_file(param_file)

param_values= morris_oat.sample(10, pf['num_vars'], num_levels=10, grid_jump=1, plot=False)
scale_samples_general(param_values, pf['bounds'])

np.savetxt('Input_params.txt', param_values, delimiter=' ')

shutil.copy('model.py', '/home/ZhiLi/CRESTHH/cresthh/UQ/test_functions/functn.py')
Y= []
for i, params in enumerate(param_values):
    # os.system('mpirun -n 40 python model.py %f %f %f %f %f %f %f > anuga.log'%(params[0],params[1],params[2],
    #                                                                 params[3],params[4],params[5],params[6]))
    os.system('mpirun -n 40 python model.py %f > anuga.log'%params)
    swwfile = 'temp.sww'
    os.system('rm temp_P*')
    splotter = anuga.SWW_plotter(swwfile, make_dir=False)
    benchmark= anuga.SWW_plotter('Coupled_10m_modified_mesh.sww', make_dir=False)
    
    OUTLET= (296090.4,3291818.4)
    xc= splotter.xc +splotter.xllcorner
    yc= splotter.yc +splotter.yllcorner
    iloc= np.argmin((xc-OUTLET[0])**2+ (yc-OUTLET[1])**2)
    stage= splotter.stage[:,iloc]
    speed= splotter.speed[:,iloc]
    stage_b= benchmark.stage[:,iloc]
    speed_b= benchmark.speed[:,iloc]
    loss= RMSE(stage*speed, stage_b*speed_b)
    print '%d/%d loss: %f'%(i,len(param_values),loss)
    Y.append(loss)

np.savetxt('Output_Sobol.txt', np.array(Y), delimiter=' ')


# def 