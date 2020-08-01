
import sys
sys.path.append('/home/ZhiLi/CRESTHH')
import cresthh
from cresthh import anuga
from cresthh import UQ
from cresthh.UQ.optimization import SCE
from cresthh.utils import flowAreaCalc
from cresthh import metrics as met
from cresthh.UQ.DoE import morris_oat
from cresthh.UQ.util import scale_samples_general, read_param_file, discrepancy
import geopandas as gpd
import shutil
import numpy as np
import model
import os
import pandas as pd

def RMSE(obs, sim):
    '''Compute the RMSE of two time series data'''
    return np.nanmean((obs-sim)**2)**.5

def metrics(x,y,obj=['nse']):
    '''
    Calculate the metrics with given objective functions

    Inputs:
    ----------------
    x - observed values;
    y - simulated values

    Returns:
    -----------------
    results - list; with respect to given metrics
    '''
    if isinstance(obj, str):
        obj= list(obj)
    
    mapper= {'nse': met.nse,
            'rmse':met.rmse,
            'peak_time_error':met.peak_time_error,
            'peak_flow_error': met.peak_flow_error,
            'pearsonr': met.pearsonr,
            'bias': met.rb}

    results= []
    for single in obj:
        try:
            mask= (~np.isnan(x)) & (~np.isnan(y))
            results.append(mapper[single](x[mask],y[mask]))
        except:
            results.append(np.nan)

    return results

def one_val(params):
    
    os.system('mpirun -n 36 python model.py %f %f %f %f %f> anuga.log'%(params[0],params[1],params[2], params[3], params[4]))
    swwfile = 'temp.sww'
    gauges= np.loadtxt('gauges.txt')

    splotter = anuga.SWW_plotter(swwfile, make_dir=False)
    xc= splotter.xc +splotter.xllcorner
    yc= splotter.yc +splotter.yllcorner
    dr= pd.date_range('20170825120000', '20170827000000', freq='120S')
    
    rmse= 0
    for gauge in gauges:
        if gauge[0]==8076700:
            df= pd.DataFrame(index=dr)
            iloc= np.argmin((xc-gauge[1])**2+ (yc-gauge[2])**2)
            obs= pd.read_csv('/home/ZhiLi/CRESTHH/data/streamGauge/%08d.csv'%(int(gauge[0])),converters={'datetime':pd.to_datetime}).set_index('datetime').loc[dr].resample('120S',
                            label='right').interpolate()
            crosssection= gpd.read_file('/home/ZhiLi/CRESTHH/data/crosssection/%08d.shp'%(int(gauge[0])))
            area= [flowAreaCalc(crosssection, splotter.stage[t,iloc]) for t in range(len(splotter.stage))]
            sim_Q= splotter.speed[:,iloc] * np.array(area)
            obs_Q= obs['discharge'].values
            #np.save('sim_Q.npy', [sim_Q, obs_Q.values])
            discharge_err= metrics(obs_Q, sim_Q, ['nse','rmse','peak_flow_error', 'peak_time_error','bias','pearsonr'])
            print discharge_err
            with open('discharge_error.txt','a') as f:
                f.write('%f,%f,%f,%f,%f,%f\n'%(discharge_err[0], discharge_err[1],discharge_err[2],discharge_err[3],
                                                discharge_err[4],discharge_err[5]))
    
    return discharge_err[0]
            
    # HWMs= pd.read_csv('/home/ZhiLi/CRESTHH/data/HoustonCase/HWM_cleaned.csv')
    # lons= HWMs.lon.values; lats= HWMs.lat.values
    # ilocs= [np.argmin((xc-lons[i])**2+ (yc-lats[i])**2) for i in range(len(lons))]

    # max_depth=np.nanmax(splotter.depth[:, ilocs], axis=0)
    # accuracy= RMSE(HWMs.HWM.values, max_depth)

    # return rmse, accuracy

def evaluate(values):
    
    Y = np.empty(values.shape[0])
    # min_nsce= np.inf
    for i, row in enumerate(values):
        nsce= one_val(row)
        print 'params: %.3f %.3f %.3f %.3f %.3f NSE: %.3f meters'%(row[0], row[1], row[2], row[3], row[4], nsce)
        Y[i]= 1-nsce
        # if nsce< min_nsce:
            # print 'updating result'
            # os.system('mv temp.sww best.sww')
            # min_nsce=nsce
    return Y

# def evaluate(values):
#     Y= np.empty(values.shape[0])
#     min_nsce= np.inf
#     for i, row in enumerate(values):
#         nsce= row[0]**2-row[1]**3+row[2]-row[3]+row[4]**4
#         Y[i]= -nsce

#     return Y


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
