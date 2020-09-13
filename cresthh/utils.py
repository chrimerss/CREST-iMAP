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


def interpolateSWW(swwfile, field, xi, yi):
    '''
    using cubic triangular interpolation to populate regular grid cells
    
    Input:
    ------------------------
    swwfile: str; output .sww file
    field: str; ['depth','velocty','SM']
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
    else:
        msg= 'not supported field'
        raise msg
        
#     interp_lin = mtri.CubicTriInterpolator(triang, z, kind='geom')
    triangles= nc['volumes'][:]
    x= nc['x'][:]
    y=nc['y'][:]
    triang= mtri.Triangulation(x, y, triangles)
    interp_lin = mtri.CubicTriInterpolator(triang, fea, kind='geom')
    xi,yi= np.meshgrid(xi,yi)
    zi_lin = interp_lin(xi, yi)
    
    return xi, yi, zi_lin

def make_Q_grids(splotter,crosssections, samples, loc='vertice'):
    '''
    make gridded discharge (cms)

    Input:
    ----------------------------
    splotter: SWW_splotter object
    crosssections: geopands object; a collection of crosssections generated by cross profiles in QGIS 3.14
    samples: int; number of points want to generate from linestring
    loc: str; either 'vertice' or 'centroid'

    Returns:
    ----------------------------
    Q_grid: similar field in splotter

    Examples:
    ----------------------------
    Q_grid= make_Q_grids(coupledSplotter, crosssections)
    '''
    
    if not isinstance(splotter, SWW_plotter):
        msg= 'expected SWW_plotter object at arg[0]'
        raise msg
    if not isinstance(crosssections, gpd.geodataframe.GeoDataFrame):
        msg= 'expected geopands data at arg[1]'
        raise msg
    if loc not in ['vertice', 'centroid']:
        msg= "expected arg[2] to be either 'vertice' or 'centroid' "
        raise msg
    if loc=='centroid':
        xc= splotter.xc + splotter.xllcorner
        yc= splotter.yc + splotter.yllcorner
        Q_grid= np.zeros(splotter.depth.shape)
    elif loc=='vertice':
        xc= splotter.x + splotter.xllcorner
        yc= splotter.y + splotter.yllcorner
        Q_grid= np.zeros((splotter.depth.shape[0], len(splotter.x)))
    for i in range(len(crosssections)):

        section= crosssections.iloc[i]
        x,y,elev= sample_points_from_line(section,samples)

        spacing= ((x[1]-x[0])**2 + (y[1]-y[0])**2)**.5
        iloc= np.argmin((xc-x.mean())**2 + (yc-y.mean())**2)
        for it in range(splotter.depth.shape[0]):
            _stage= splotter.stage[it,iloc]
            _speed= splotter.speed[it,iloc]
            _mask= np.where(elev<_stage)[0]
            _area= ((_stage-elev[_mask]) * spacing).sum()
            Q_grid[it,iloc]=_area*_speed
    return Q_grid
        
    
 