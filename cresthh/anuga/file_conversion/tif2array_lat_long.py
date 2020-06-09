__author__ = 'Allen Zhi Li'
__date__= '2020/06/08'

import numpy as np

from osgeo import gdal

from pyproj import Proj, CRS, transform

from affine import Affine

def tif2array_lat_long(filename, variable_name='elevation',
              easting_min=None, easting_max=None,
              northing_min=None, northing_max=None,
             use_cache=False, verbose=False, proj=None, points=None):
    
    import os
    wgs84= CRS('EPSG:4326')
    UTM= CRS(proj)
    # print points
    utm_to_84_lons, utm_to_84_lats= transform(UTM,wgs84,points[:,0], points[:,1])

    raster= gdal.Open(filename)
    ncols= raster.RasterXSize
    nrows= raster.RasterYSize
    # x_origin, x_res, _, y_origin, _, y_res= raster.GetGeoTransform()
    NODATA_value= raster.GetRasterBand(1).GetNoDataValue()
    Z= raster.ReadAsArray()
    Z= np.where(Z==NODATA_value, np.nan, Z)
    
    transformer= Affine.from_gdal(*raster.GetGeoTransform())
    ilocs= np.array(~ transformer * (utm_to_84_lats,utm_to_84_lons))
    # print utm_to_84_lats, utm_to_84_lons
    icols= ilocs[0,:].astype(int); irows= ilocs[1,:].astype(int)
    # print Z.shape, icols.max(), irows.max()

    #safe return
    # tobe_return= np.zeros(len(points)) * np.nan

    return Z[irows, icols]

    
    
    # if y_res<0:
    #     xllcrn= x_origin;yllcrn=y_origin+y_res*(nrows-1);xurcrn=x_origin+x_res*(ncols-1);yurcrn=y_origin;
    #     # xllcrn= x_origin;yllcrn=y_origin;xurcrn=x_origin+x_res*(ncols-1);yurcrn=y_origin+y_res*(nrows-1);
    #     # print xllcrn, xurcrn, yllcrn, yurcrn
    #     # llcrn= myproj(xllcrn,yllcrn); urcrn=myproj(xurcrn, yurcrn)
    #     # print llcrn, urcrn
    #     x= np.linspace(xllcrn,xurcrn, ncols)
    #     y= np.linspace(yllcrn,yurcrn, nrows)
    #     x,y= myproj(x,y)
        
    #     Z= np.flip(Z, axis=0)
    #     Z= Z.transpose()
    # elif y_res>=0:
    #     xllcrn= x_origin;yllcrn=y_origin;xurcrn=x_origin+x_res*(ncols-1);yurcrn=y_origin+y_res*(nrows-1);
    #     # llcrn= myproj(xllcrn,yllcrn); urcrn=myproj(xurcrn, yurcrn)
    #     x= np.linspace(xllcrn,xurcrn, ncols)
    #     y= np.linspace(yllcrn,yurcrn, nrows)
    #     x,y=myproj(x,y)
    #     Z= Z.transpose()
    
    
    # return x, y, Z
    
    