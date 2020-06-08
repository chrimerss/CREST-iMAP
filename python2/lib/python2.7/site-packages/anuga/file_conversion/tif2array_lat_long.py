__author__ = 'Allen Zhi Li'
__date__= '2020/06/08'
__version__=0.1

import numpy as np

from osgeo import gdal

from pyproj import Proj

def tif2array_lat_long(filename, variable_name='elevation',
              easting_min=None, easting_max=None,
              northing_min=None, northing_max=None,
             use_cache=False, verbose=False, proj=None):
    
    import os
    raster= gdal.Open(filename)
    ncols= raster.RasterXSize
    nrows= raster.RasterYSize
    x_origin, x_res, _, y_origin, _, y_res= raster.GetGeoTransform()
    NODATA_value= raster.GetRasterBand(1).GetNoDataValue()
    Z= raster.ReadAsArray()
    Z= np.where(Z==NODATA_value, np.nan, Z)

    myproj= Proj(proj)
    
    if y_res<0:
        xllcrn= x_origin;yllcrn=y_origin+y_res*(nrows-1);xurcrn=x_origin+x_res*(ncols-1);yurcrn=y_origin;
        # xllcrn= x_origin;yllcrn=y_origin;xurcrn=x_origin+x_res*(ncols-1);yurcrn=y_origin+y_res*(nrows-1);
        # print xllcrn, xurcrn, yllcrn, yurcrn
        llcrn= myproj(xllcrn,yllcrn); urcrn=myproj(xurcrn, yurcrn)
        # print llcrn, urcrn
        x= np.linspace(llcrn[0],urcrn[0], ncols)
        y= np.linspace(llcrn[1],urcrn[1], nrows)
        
        Z= np.flip(Z, axis=0)
        Z= Z.transpose()
    elif y_res>=0:
        xllcrn= x_origin;yllcrn=y_origin;xurcrn=x_origin+x_res*(ncols-1);yurcrn=y_origin+y_res*(nrows-1);
        llcrn= myproj(xllcrn,yllcrn); urcrn=myproj(xurcrn, yurcrn)
        x= np.linspace(llcrn[0],urcrn[0], ncols)
        y= np.linspace(llcrn[1],urcrn[1], nrows)
        Z= Z.transpose()
    
    
    return x, y, Z
    
    