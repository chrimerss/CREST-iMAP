#!/home/ZhiLi/CRESTHH/python2/bin/python2
'''
A command line tool to get reduced geotiffs quickly

__author__: Zhi Li
__Date__: 2021/02/07
'''
import argparse
import numpy as np

import sys
sys.path.append('/home/ZhiLi/CRESTHH')
from cresthh.anuga.file_conversion.sww2dem import sww2dem
from cresthh.anuga import SWW_plotter
from netCDF4 import Dataset
from osgeo import gdal
import os
import numpy as np
import matplotlib.tri as mtri

def export_tif(dst, lons, lats, arr,projection, res):
    # print arr.shape, lons.shape, lats.shape
    rows, cols= arr.shape
    driver = gdal.GetDriverByName("GTiff")
    outdata = driver.Create(dst, cols, rows, 1, gdal.GDT_Float32)
    outdata.SetGeoTransform([lons[0], res, 0, lats[0], 0, res])##sets same geotransform as input
    # outdata.SetProjection(projection)##sets same projection as input
    outdata.GetRasterBand(1).WriteArray(arr)
    outdata.GetRasterBand(1).SetNoDataValue(-9999)##if you want these values transparent
    outdata.FlushCache() ##saves to disk!!
    outdata = None
    band=None
    ds=None

parser= argparse.ArgumentParser(description='Quick retrieval of flood depth')
parser.add_argument('--sww', type=str, metavar='sww file', required=True,
                    help='SWW file to be retrieved from')
parser.add_argument('--dst', type=str, metavar='destination', required=True,
                    help='File path to store transformed file')

parser.add_argument('--tif', type=bool, metavar='output GeoTiff', required=False,
                    default=True, help='Whether output tif format, default True')

parser.add_argument('--quantity', type=str, metavar='output quantity', required=False,
                    default='depth', help= 'which quantity to output, default depth')

parser.add_argument('--reduce', type=str, metavar='reduction', required=False,
                    default='max', help= 'choose a method to reduce time dimension, default max.')

parser.add_argument('--tr', type=float, metavar='resolution', required=False,
                    default=None, help= 'choose whether to rescale image, default 10m; method: bilinear interpolation')

parser.add_argument('--s_srs', type=str, required=False, default="EPSG:32215", help= 'source projection system')
parser.add_argument('--t_srs', type=str, required=False, default="EPSG:4326", help= 'target projection system')
parser.add_argument('--interp', type=str, required=False, default="square", help= 'interpolation method')

args= parser.parse_args()
sww_file= args.sww
dst= args.dst
isTiff= args.tif
toReduce= args.reduce
res= args.tr
quantity= args.quantity
s_srs= args.s_srs
t_srs= args.t_srs
interp= args.interp
base_name=dst.split('.')[0]
if quantity not in ['depth', 'xmomentum', 'elevation', 'ymomentum', 'excRain']:
    raise ValueError('expected quantity in ["depth", "xmomentum", "elevation", "ymomentum", "excRain"]')

if toReduce=='max':
    reduce=max
elif toReduce=='mean':
    reduce=mean
else:
    reduce= int(toReduce) #choose time series

if res is None:
    res=10

if interp=='square':
    #produce .asc
    sww2dem(sww_file, base_name+'.asc', quantity=quantity, verbose=True, reduction=reduce, cellsize=res)
    if isTiff:
        os.system('gdalwarp -co COMPRESS=LZW -ot Float32 -s_srs %s -t_srs %s %s %s'%(s_srs, t_srs, base_name+'.asc', base_name+'.tif'))
        os.system('rm %s'%(base_name+'.asc'))
        os.system('rm %s'%(base_name+'.prj'))
elif interp=='cubic':
    from cresthh.anuga.file.netcdf import NetCDFFile
    p = NetCDFFile(sww_file)
    z= np.array(p.variables['stage'])-\
             np.array(p.variables['elevation'])
    x = np.array(p.variables['x'])
    y = np.array(p.variables['y'])
    triangles = np.array(p.variables['volumes'])
    triang = mtri.Triangulation(x, y, triangles)
    xi, yi= np.meshgrid(np.arange(0, x.max()+res, res),
                        np.arange(0, y.max()+res, res))
    if isinstance(toReduce,int):
        _z= z[toReduce]
    else:
        _z= z.max(axis=0)
    interp= mtri.CubicTriInterpolator(triang, _z, kind='geom')
    zi_interp= interp(xi,yi)
    xllcorner = p.xllcorner
    yllcorner = p.yllcorner
    xi += xllcorner
    yi += yllcorner
    export_tif(base_name+'.asc', xi[0,:], yi[:,0], zi_interp, s_srs, res)
    os.system('gdalwarp -co COMPRESS=LZW -ot Float32 -s_srs %s -t_srs %s %s %s'%(s_srs, t_srs, base_name+'.asc', base_name+'.tif'))
else:
    raise ValueError('invalid argument, only supports LSI and cubic')



    # os.system('rm %s && mv %s %s'%(dst, dst+'.temp',dst))
print('Completed! output file name: %s'%dst)

