# Initialize grid class
from osgeo import gdal
from CREST.flow import Flow
from logs import logger
import numpy as np

class Grid(object):
    """Construct georeferenced grids according to DEM file"""
    def __init__(self, **pth):
        super(Grid, self).__init__()
        DEM= pth['DEMpath']
        flow= Flow(demFilePath= DEM)
        xsize, ysize, x_res, y_res, llcrn= self.geoinfo(DEM)
        self.nrows= ysize
        self.ncols= xsize
        self.states= self.intialize_crest_states()
        self.fluxes= self.initialize_crest_fluxes()
        self.static= {'DEM': flow.dem,
                    'flow_dir': flow.dir,
                    'flow_acc': flow.acc,
                    'xsize': xsize,
                    'ysize': ysize,
                    'x_res': x_res,
                    'y_res': y_res,
                    'llcrn': llcrn}
        # logger.warning('Completed grid initialization: %s'%([self.data[key] for key in self.data if self.data[key] is not None]))
        del DEM, flow
    
    def geoinfo(self, dem):
        if dem.endswith('.tif'):
            raster= gdal.Open(dem)
            geotransform= raster.GetGeoTransform()
            xsize= raster.RasterXSize
            ysize= raster.RasterYSize
            x_reso= geotransform[1]
            y_reso= geotransform[-1]
            llcrn= (geotransform[0], geotransform[3])

        else:
            # TODO read asc file or h5
            pass

        return (xsize, ysize, x_reso, y_reso, llcrn)

    def update(self, field, dtype):

        self.data[fieled]=np.zeros((self.nrows, self.ncols), dtype= dtype)

    def intialize_crest_states(self):
        states= np.zeros((self.nrows,
                 self.ncols), dtype= {
                     'names': ('SS0', 'SI0', 'W0'),
                     'formats': ('f4', 'f4', 'f4')
                 })

        return states


    def initialize_crest_fluxes(self):
        fluxes= np.zeros((self.nrows,
                 self.ncols), dtype= {
                     'names': ('RI', 'RS'),
                     'formats': ('f4', 'f4')
                 })

        return fluxes

    @property
    def fluxes(self):
        """The fluxes property."""
        return self.fluxes

    @fluxes.setter
    def fluxes(self, *args):
        m,n,RI, RS= args
        self.fluxes['RI'][m,n]= RI
        self.fluxes['RS'][m,n]= RS

    @property
    def states(self):
        """The states property."""
        return self.states

    @states.setter
    def states(self, *args):
        m,n, SS, SI, W = args
        self.states['SS0'][m,n]= SS
        self.states['SI0'][m,n]= SS
        self.states['W0'][m,n]= SS
