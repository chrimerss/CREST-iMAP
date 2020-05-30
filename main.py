# The coupling hydrologic/hydrodynamic model framework
from CREST.model import CREST
from CREST.flow import FLOW
from grid import Grid
from config import read_config_file
from logs import logger

class HHModel(object):
    """docstring for HHModel."""
    def __init__(self):
        super(HHModel, self).__init__()
        self.syspar= read_config_file()
        self.grids= Grid(self.syspar['DEMfile'])
        self.mesh= None
        
    def step():
        pass
        