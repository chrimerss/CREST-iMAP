'''
This module stores some toolkits to aid results interpretation
'''

__date__='2020/06/24'
__author__='Allen Zhi Li'

import geopandas as gpd
import pandas as pd
import numpy as np
from cresthh.anuga import SWW_plotter
from netCDF4 import Dataset

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
    swwfile - generated .sww file name or Dataset
    field - list; field names to extract; supported ['depth','speed','stage','soil_moisture']
    obs_loc - tuple; location of observational point (on par with project projections)
    start_time - pandas time index; begin time

    Returns:
    ----------------------
    results - pandas object
    '''
    if isinstance(swwfile, str):
        splotter= SWW_plotter(swwfile, start_time=start_time)
        depth= splotter.depth
        speed= splotter.speed
        stage= splotter.stage
        time= splotter.time
        soil= splotter.SM
        xc= splotter.xc+ splotter.xllcorner
        yc= splotter.yc+ splotter.yllcorner
    else:
        splotter= swwfile
        depth= splotter['depth'][:]
        speed= splotter['speed'][:]
        # stage= splotter['stage'][:]
        time= splotter['time'][:]
        soil= splotter['SM'][:]
        xc= splotter['x']+splotter.xllcorner
        yc= splotter['y']+splotter.yllcorner
    
    iloc= np.argmin( (xc-obs_loc[0])**2 + (yc-obs_loc[1])**2 )
    
    
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
        # if field=='excess rain':
        #     results['excess rain']= rain[:,iloc]

    return results

def sample_points_from_line(line, samples):
    '''generate point samples from a linestring'''
    llcorner= np.array(line.geometry.coords)[0]
    urcorner= np.array(line.geometry.coords)[1]
    x= np.linspace(llcorner[0], urcorner[0],samples)
    y= np.linspace(llcorner[1], urcorner[1],samples)
    values= line.iloc[3:-1].values
    
    return x, y, values


def interpolateSWW(swwfile, xi, yi):
    '''
    using cubic triangular interpolation to populate regular grid cells
    
    Input:
    ------------------------
    swwfile: str; output .sww file
    xi: np.ndarray 1D; the longitudes
    yi: np.ndarray 1D; the latitudes

    Output:
    ------------------------
    xi: np.ndarray 2D; the meshgrided longitudes
    yi: np.ndarray 2D; the meshgrided latitudes
    zi_lin: np.ndarray 2D; the interpolated field

    Examples:
    ------------------------
    xi,yi,MD_benchmark= interpolate('Coupled_10m_modified_mesh.sww', np.arange(0,38000,10), np.arange(0,25000,10))
    '''
    from netCDF4 import Dataset
    import matplotlib.tri as mtri
    nc= Dataset(swwfile)
    if isinstance(field, str):
        if field=='depth':
            fea= nc['stage'][:].max(axis=0)- nc['elevation'][:]
    elif isinstance(field, np.ndarray):
        
#     interp_lin = mtri.CubicTriInterpolator(triang, z, kind='geom')
    triangles= nc['volumes'][:]
    x= nc['x'][:]
    y=nc['y'][:]
    triang= mtri.Triangulation(x, y, triangles)
    interp_lin = mtri.CubicTriInterpolator(triang, fea, kind='geom')
    xi,yi= np.meshgrid(xi,yi)
    zi_lin = interp_lin(xi, yi)
    
    return xi, yi, zi_lin
 