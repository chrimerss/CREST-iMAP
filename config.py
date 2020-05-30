# Read config file 
# TODO
import configparser

class Config(object):
    """Read configuration file"""
    def __init__(self, file):
        super(Config, self).__init__()
        config= configparser.RawConfigParser()
        config.optionxform = str 
        config.read(file)
        self._crest= self.getCrestParams(config)
        self._HH= self.getHHParams(config)
        self._sys= self.getSysParams(config)
        
    def getCrestParams(self, config):

        return {key:config['CREST'][key] for key in config['CREST'].keys()}

    def getHHParams(self, config):
        
        return {key:config['HH'][key] for key in config['HH'].keys()}
    
    def getSysParams(self, config):
        return {key:config['System'][key] for key in config['System'].keys()}

    @property
    def crest(self):
        return self._crest

    @@property
    def HH(self):
        """The HH property."""
        return self._HH
    @HH.setter
    def HH(self, value):
        self._HH = value

    @@property
    def sys(self):
        """The sys property."""
        return self._sys
    @sys.setter
    def sys(self, value):
        self._sys = value