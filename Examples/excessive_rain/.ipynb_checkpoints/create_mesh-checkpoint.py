import sys
sys.path.append('../../')
import cresthh
from cresthh import anuga
from osgeo import gdal
from glob import glob
from affine import Affine
import geopandas as gpd
from pyproj import Proj, CRS, transform
import numpy as np

study_area= gpd.read_file('/home/ZhiLi/CRESTHH/data/HoustonCase/study_area/Houston_basin.shp')
inner_zone_channel= gpd.read_file('/home/ZhiLi/CRESTHH/data/HoustonCase/river_buffer/Houston_river_buffer.shp')
inner_zone_plain= gpd.read_file('/home/ZhiLi/CRESTHH/data/HoustonCase/flood_plain/Houston_plain_buffer.shp')
topography_file = '/hydros/ZhiLi/conditioned_DEM.tif'
base_resolution = 1000000 #1km
channel_resolution= 100 #10 m
floodPlainResolution= 10000 #100m
proj= "+proj=utm +zone=15, +south +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
wgs84= CRS('EPSG:4326')
UTM= CRS(proj)


lons= np.array(study_area.exterior[0].coords)[:,0]; lats=np.array(study_area.exterior[0].coords)[:,1]
myProj = Proj("+proj=utm +zone=15, +south +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
utm_coords_domain= [myProj(lon,lat) for (lon, lat) in zip(lons, lats)]
# lons= np.array(inner_zone_channel.geometry[0])[:,0]; lats=np.array(inner_zone_channel.geometry[0])[:,1]
coords_inner_channel= np.concatenate([np.array(inner_zone_channel.boundary[0][i].coords) for i in range(len(inner_zone_channel.boundary[0]))])
utm_coords_channel= [myProj(lon,lat) for (lon, lat) in coords_inner_channel]
coords_inner_plain= np.concatenate([np.array(inner_zone_plain.boundary[0][i].coords) for i in range(len(inner_zone_plain.boundary[0]))])
# lons= np.array(inner_zone_plain.geometry[0])[:,0]; lats=np.array(inner_zone_plain.geometry[0])[:,1]
utm_coords_plain= [myProj(lon,lat) for (lon, lat) in coords_inner_plain]

domain = anuga.create_domain_from_regions(
            utm_coords_domain,
            boundary_tags={'bottom': [0]},
            maximum_triangle_area=1000000,
            interior_regions=[[utm_coords_channel, channel_resolution],
                              [utm_coords_plain, floodPlainResolution]],
            mesh_filename='Houston.msh'
            )

#domain.set_name('Houston') # Name of sww file
#dplotter = anuga.Domain_plotter(domain) 
