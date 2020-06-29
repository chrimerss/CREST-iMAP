'''
This module stores some toolkits to aid results interpretation
'''

__date__='2020/06/24'
__author__='Allen Zhi Li'

import geopandas as gpd
import pandas as pd
import numpy as np
from cresthh.anuga import SWW_plotter

def flowAreaCalc(samples, stage):
    '''
    calculate the lateral flow area based on the cross-section profile and depth
    first-order approximation

    Args:
    ---------------------
    :samples - geopandas Point object, stores elevation and geometry
    :depth - simulated channel depth

    Returns:
    ---------------------
    :area - area of unit determined by input
    '''
    if not isinstance(samples, gpd.geodataframe.GeoDataFrame):
        raise ValueError('Expected argument 1 to be geopandas point dataframe, but got %s'%type(samples))
    else:
        elev= samples.Value
        spacing= samples.distance(samples.shift()).iloc[1]
        mask= np.where(elev<stage)[0]
        area= ((stage-elev[mask]) * spacing).sum()
        return area

def processSWW(swwfile, fields, obs_loc, start_time=None):
    '''
    post-process generated SWW file and extract corresponding field at the observational point

    Args:
    ----------------------
    swwfile - generated .sww file name
    field - list; field names to extract; supported ['depth','speed','stage','soil_moisture']
    obs_loc - tuple; location of observational point (on par with project projections)
    start_time - pandas time index; begin time

    Returns:
    ----------------------
    results - pandas object
    '''
    splotter= SWW_plotter(swwfile, start_time=start_time)
    xc= splotter.xc+ splotter.xllcorner
    yc= splotter.yc+ splotter.yllcorner
    iloc= np.argmin( (xc-obs_loc[0])**2 + (yc-obs_loc[1])**2 )
    depth= splotter.depth
    speed= splotter.speed
    stage= splotter.stage
    time= splotter.time
    soil= splotter.SM
    results= pd.DataFrame(index=time)

    for field in fields:
        if field == 'depth':
            results['depth']= depth[:, iloc]
        if field == 'speed':
            results['speed']= speed[:,iloc]
        if field=='stage':
            results['stage']= stage[:,iloc]
        if field=='soil moisture':
            results['soil moisture']= soil[:,iloc]

    return results