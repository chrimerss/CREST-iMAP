# Initialize grid class
from osgeo import gdal
from osgeo.gdal import Translate
from CREST.flow import Flow
from logs import formatter
import numpy as np


LOGGER= formatter(__name__)

class Grid(object):
    """Construct georeferenced grids according to DEM file"""
    def __init__(self, crest_param=None, **pth):
        super(Grid, self).__init__()
        DEM= pth['DEMpath']
        flow= Flow(demFilePath= DEM)
        xsize, ysize, x_res, y_res, llcrn, proj= self.geoinfo(DEM)
        llx= llcrn[0]; lly= llcrn[1]
        ulx= llx;lrx=llx+x_res*xsize;
        if y_res<=0: uly= llcrn[1] + (-y_res)*ysize; lry=lly
        elif y_res>0: uly= llcrn[1] + (y_res)*ysize; lry=lly
        ext= (ulx, uly, lrx, lry)
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
                    'llcrn': llcrn,
                    'proj': proj}
        # logger.warning('Completed grid initialization: %s'%([self.data[key] for key in self.data if self.data[key] is not None]))
        del DEM, flow
        
        if isinstance(crest_param['RainFact'], float): #if no a-prior database
            self._crest_params= self.assign_grids(self.nrows, self.ncols, crest_param)
        elif isinstance(crest_param['RainFact'], str): #if a-prior database is provided
            #TODO this function doesnot work -20200601
            self._crest_params= self.resample(ext, (x_res, y_res), xsize, ysize,crest_param)
        
        #check if successfully assigned
        

    
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
            proj= raster.GetProjection()

        else:
            # TODO read asc file or h5
            pass

        return (xsize, ysize, x_res, y_res, llcrn, proj)

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
        args= args[0]
        m,n,RI, RS= args
        self._fluxes['RI'][m,n]= RI
        self._fluxes['RS'][m,n]= RS

    @property
    def states(self):
        """The states property."""
        return self._states

    @states.setter
    def states(self, *args):
        args= args[0]
        m,n, SS, SI, W = args
        self._states['SS0'][m,n]= SS
        self._states['SI0'][m,n]= SI
        self._states['W0'][m,n]= W

    @property
    def crest_params(self):
        """The states property."""
        return self._crest_params

    @crest_params.setter
    def crest_params(self, *args):
        args= args[0]
        m,n, SS0, SI0, W0 = args
        self._crest_params['SS0'][m,n]= SS
        self._crest_params['SI0'][m,n]= SI
        self._crest_params['W0'][m,n]= W0

    @staticmethod
    def assign_grids(nrows, ncols, param):
        new_param= np.zeros((nrows, ncols),
                            dtype={'names': ('RainFact', 'Ksat',
                            'WM','B', 'IM', 'KE', 'coeM','expM', 'coeR',
                            'coeS', 'KS', 'KI'),
                                   'formats': ['f4']*12})
        # print(new_param)
        for key in param.keys():
            new_param[key]= np.ones((nrows, ncols))*param[key]

        return new_param

    @staticmethod
    def resample(ext, reso, xsize, ysize, rasterName, method='nearest', ):
        '''Use gdal.translate to resample raster data '''
        
        if Translate(srcDS=rasterName, noData=-9999, 
                  projWin=ext, height=ysize, width= xsize,destName='temp.tif',resampleAlg=method):
            raster= gdal.Open('temp.tif')
            return raster
        else:
            raise ValueError('Error in resampling')