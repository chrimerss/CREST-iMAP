
import sys
sys.path.append('/home/ZhiLi/CRESTHH')
import cresthh
from cresthh import anuga
from cresthh import UQ
from cresthh.UQ.optimization import SCE

from cresthh.UQ.DoE import morris_oat
from cresthh.UQ.util import scale_samples_general, read_param_file, discrepancy
import shutil
import numpy as np
import model
import os
import pandas as pd

def RMSE(obs, sim):
    '''Compute the RMSE of two time series data'''
    return np.nanmean((obs-sim)**2)**.5

def one_val(params):
    
    os.system('mpirun -n 36 python model.py %f %f %f > anuga.log'%(params[0],params[1],params[2]))
    swwfile = 'temp.sww'
    gauges= np.loadtxt('gauges.txt')

    splotter = anuga.SWW_plotter(swwfile, make_dir=False)
    xc= splotter.xc +splotter.xllcorner
    yc= splotter.yc +splotter.yllcorner
    dr= pd.date_range('20170825', '20170830', freq='120S')
    
    rmse= 0
    for gauge in gauges:
        df= pd.DataFrame(index=dr)
        iloc= np.argmin((xc-gauge[1])**2+ (yc-gauge[2])**2)
        obs= pd.read_csv('/home/ZhiLi/CRESTHH/data/streamGauge/%08d.csv'%(int(gauge[0])),converters={'datetime':pd.to_datetime}).set_index('datetime').resample('120S',
                         label='right').interpolate()
        df['sim']= splotter.stage[:,iloc]
        df['obs']= obs['stage']
        rmse+= RMSE(df.sim, df.obs)

    return rmse

def evaluate(values):
    Y = np.empty([values.shape[0]])
    min_rmse= np.inf
    for i, row in enumerate(values):
        rmse= one_val(row)
        print 'RMSE: %.3f meters'%rmse
        Y[i]= rmse
        if rmse< min_rmse:
            os.system('mv temp.sww best.sww')
            min_rmse=rmse
    return Y


# Read in parameter file
param_file = 'params.txt'
pf= read_param_file(param_file)

# param_values= morris_oat.sample(10, pf['num_vars'], num_levels=4, grid_jump=2)
# scale_samples_general(param_values, pf['bounds'])

# np.savetxt('Input_params.txt', param_values, delimiter=' ')

# shutil.copy('model.py', '/home/ZhiLi/CRESTHH/cresthh/UQ/test_functions/functn.py')
bl=np.empty(0)
bu=np.empty(0)
for i, b in enumerate(pf['bounds']):
    bl = np.append(bl, b[0])
    bu = np.append(bu, b[1])

bestx,bestf,BESTX,BESTF,ICALL= SCE.sceua(bl, bu, pf, ngs=2, func=evaluate, plot=False)
np.save('resultsX.npy', BESTX)
np.save('resultsF.npy', BESTF)
# def 