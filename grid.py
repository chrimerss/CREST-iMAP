# Initialize grid class
from osgeo import gdal
from CREST.flow import Flow
from logs import logger


class Grid(object):
    """Construct georeferenced grids according to DEM file"""
    def __init__(self, **pth):
        super(Grid, self).__init__()
        DEM= pth['DEMpath']
        flow= Flow(demFilePath= DEM)
        xsize, ysize, x_res, y_res, llcrn= self.geoinfo(DEM)
        self.nrows= ysize
        self.ncols= xsize
        states= self.intialize_crest_states()
        fluxes= self.initialize_crest_fluxes()
        self.data= {'DEM': flow.dem,
                    'flow_dir': flow.dir,
                    'flow_acc': flow.acc,
                    'states': states,
                    'fluxes': fluxes,
                    'xsize': xsize,
                    'ysize': ysize,
                    'x_res': x_res,
                    'y_res': y_res,
                    'llcrn': llcrn}
        logger.warning('Completed grid initialization: %s'%([self.data[key] for key in self.data if self.data[key] is not None]))
        del DEM, flow, states, fluxes
    
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
        pass

    def initialize_crest_fluxes(self):
        pass
