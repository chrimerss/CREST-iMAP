'''
This module stores some toolkits to aid results interpretation
'''

__date__='2020/06/24'
__author__='Allen Zhi Li'

import geopandas as gpd
import numpy as np

def flowAreaCalc(samples, depth):
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
        mask= np.where(elev<depth)[0]
        area= ((depth-elev[mask]) * spacing).sum()
        return area
