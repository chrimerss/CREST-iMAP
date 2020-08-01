import sys
sys.path.append('/home/ZhiLi/CRESTHH')
import cresthh
from cresthh import anuga
from cresthh import UQ
# from cresthh.UQ.RSmodel import RF
from cresthh import metrics as met
from cresthh.anuga import SWW_plotter
from cresthh.utils import flowAreaCalc
from cresthh.UQ.DoE import lhs
from cresthh.UQ.util import scale_samples_general, read_param_file, discrepancy
import shutil
import numpy as np
import model
import os
import pandas as pd
import geopandas as gpd
import argparse
# import warnings
# warnings.filterwarnings

def load_observations(dr):
    '''

    Returns:
    -------------------
    observations: list; [Dataframe, lon, lat]
    '''
    observations= {}
    gauges= np.loadtxt('gauges.txt')
    for gauge in gauges:
        # df= pd.DataFrame(index=dr)
        # iloc= np.argmin((xc-gauge[1])**2+ (yc-gauge[2])**2)
        _obs= pd.read_csv('/home/ZhiLi/CRESTHH/data/streamGauge/%08d.csv'%(int(gauge[0])),
                        converters={'datetime':pd.to_datetime}).set_index('datetime').resample('120S',
                         label='right').interpolate().loc[dr]
        observations['%08d'%(int(gauge[0]))]= [_obs, gauge[1], gauge[2]]

    return observations

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

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('init', type=int)
    init_para= parser.parse_args().init


    if init_para or not os.path.exists('Input_params.txt'):

        print "Parameter file not found, initiate..."

        #DoE
        param_file = 'params.txt' #read parameter file
        pf= read_param_file(param_file)

        param_values= lhs.sample(200, pf['num_vars'], plot=False) #sample the parameters with 
        scale_samples_general(param_values, pf['bounds'])

        np.savetxt('Input_params.txt', param_values, delimiter=' ')

    else:
        print 'Parameter file detected...'
        param_values= np.loadtxt('Input_params.txt', delimiter=' ')

    dr= pd.date_range('20170825120000', '20170827000000', freq='120S')
    gauges= load_observations(dr)


    for i, params in enumerate(param_values):
        print '%d/%d'%(i,len(param_values))
        os.system('mpirun -n 36 python model.py %f %f %f %f > anuga.log'%(params[0],params[1],params[2], params[3]))
        
        sww_file= 'temp.sww'
        splotter= SWW_plotter(sww_file,make_dir=False)
        xc= splotter.xc + splotter.xllcorner
        yc= splotter.yc + splotter.yllcorner
        for gauge_name in gauges.keys():
            if os.path.exists(gauge_name+'.csv'):
                df= pd.read_csv(gauge_name+'.csv')
            else:
                df= pd.DataFrame(index=dr)
            # crosssection= gpd.read_file('/home/ZhiLi/CRESTHH/data/crosssection/%s.shp'%gauge_name)
            iloc= np.argmin((gauges[gauge_name][1]-xc)**2+(gauges[gauge_name][2]-yc)**2)
            # area= [flowAreaCalc(crosssection, splotter.stage[t,iloc]) for t in range(len(splotter.stage))]
            # sim_Q= splotter.depth[:,iloc] * np.array(area)
            sim_H= splotter.stage[:,iloc]
            # discharge_err= metrics(gauges[gauge_name][0].discharge.values, sim_Q, ['nse','rmse','peak_flow_error', 'peak_time_error','bias','pearsonr'])
            stage_err= metrics(gauges[gauge_name][0].stage.values, sim_H, ['rmse','bias','pearsonr','peak_flow_error','peak_time_error'])
            # with open('discharge_error.txt','a') as f:
                # f.write('%d,%f,%f,%f,%f,%f,%f\n'%(i, discharge_err[0], discharge_err[1],discharge_err[2],discharge_err[3],
                                                # discharge_err[4],discharge_err[5]))
            with open('stage_error.txt','a') as f:
                f.write('%d,%f,%f,%f,%f,%f\n'%(i, stage_err[0], stage_err[1],stage_err[2],stage_err[3],
                                                stage_err[4]))  

            df.loc[:,i]=sim_H         
            df.to_csv(gauge_name+'.csv')                                     
