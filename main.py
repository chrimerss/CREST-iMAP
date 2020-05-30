# The coupling hydrologic/hydrodynamic model framework
from CREST.model import CREST
from CREST.flow import FLOW
from grid import Grid
from config import Config
from logs import logger

# GOBAL VAR
CONFIG_FILE= 'config.txt'

class HHModel(object):
    """docstring for HHModel."""
    def __init__(self):
        super(HHModel, self).__init__()
        self.syspar= Config(CONFIG_FILE)
        self.grids= Grid(self.syspar['DEMfile'])
        self.grids.update('crest_param', self.syspar)
        self.mesh= None
        self.crest= CREST(self.grids, self.syspar.crest_params)

    def step(self, timestamp):
        

    def run(self):
        pass
        