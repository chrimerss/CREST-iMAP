# Initialize grid class
from osgeo import gdal
from CREST.flow import Flow
from logs import formatter
import numpy as np

LOGGER= formatter(__name__)

class Grid(object):
    """Construct georeferenced grids according to DEM file"""
    def __init__(self, **pth):
        super(Grid, self).__init__()
        DEM= pth['DEMpath']
        flow= Flow(demFilePath= DEM)
        xsize, ysize, x_res, y_res, llcrn= self.geoinfo(DEM)
        self.nrows= ysize
        self.ncols= xsize
        self._states= self.intialize_crest_states()
        self._fluxes= self.initialize_crest_fluxes()
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
            xsize= int(raster.RasterXSize)
            ysize= int(raster.RasterYSize)
            x_res= geotransform[1]
            y_res= geotransform[-1]
            if y_res>0: llcrn= (geotransform[0], geotransform[3])
            elif y_res<=0: llcrn= (geotransform[0], geotransform[3]+geotransform[-1]*ysize)

        else:
            # TODO read asc file or h5
            pass

        return (xsize, ysize, x_res, y_res, llcrn)

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
        return self._fluxes

    @fluxes.setter
    def fluxes(self, *args):
        m,n,RI, RS= args
        self._fluxes['RI'][m,n]= RI
        self._fluxes['RS'][m,n]= RS

    @property
    def states(self):
        """The states property."""
        return self._states

    @states.setter
    def states(self, *args):
        print(args)
        m,n, SS, SI, W = args
        self._states['SS0'][m,n]= SS
        self._states['SI0'][m,n]= SS
        self._states['W0'][m,n]= SS
