# Read config file 
# TODO
import configparser
import dateparser
import datetime
import distutils
from logs import formatter

LOGGER= formatter(__name__)

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
        self._forcing= self.getForcingParams(config)
        # print('forcing', self._forcing)
        LOGGER.warning('\n\================================\n\
                        ===========CRESTHH==============\n\
                        ================================\n\
                        System parameters: %s\nCREST parameters: %s\n\
                        Forcing folders: %s'%(self._sys,self._crest, self._forcing))
        
    def getCrestParams(self, config):
        crest_params= {key:config['CREST'][key] for key in config['CREST'].keys()}
        apriori= distutils.util.strtobool(crest_params.pop('apriori'))
        
        # print('apriori:', apriori)
        if apriori:
            return {key:str(config['CREST'][key]) for key in crest_params.keys()}
        else:
            return {key:float(config['CREST'][key]) for key in crest_params.keys()}
            

    def getHHParams(self, config):
        
        return {key:float(config['HH'][key]) for key in config['HH'].keys()}
    
    def getSysParams(self, config):
        # def _resolveTimeStep(string):
            # if string.endswith('H'):
            #     return datetime.timedelta(hours=int(string[:-1]))
            # elif string.endswith('M'):
            #     return datetime.timedelta(minutess=int(string[:-1]))
            # elif string.endswith('S'):
            #     return datetime.timedelta(seconds=int(string[:-1]))
        mapper= {'cores': int,
                 'TimeStep': str,
                 'start': dateparser.parse,
                 'end': dateparser.parse}
        

        return {key:mapper[key](config['System'][key]) for key in config['System'].keys()}

    def getForcingParams(self, config):
        return {key:config['Forcing'][key] for key in config['Forcing'].keys()}

    @property
    def crest(self):
        return self._crest
    @crest.setter
    def crest(self, value):
        self._HH = value        

    @property
    def HH(self):
        """The HH property."""
        return self._HH
    @HH.setter
    def HH(self, value):
        self._HH = value

    @property
    def sys(self):
        """The sys property."""
        return self._sys
    @sys.setter
    def sys(self, value):
        self._sys = value

    @property
    def forcing(self):
        """The forcing property."""
        return self._forcing
    @forcing.setter
    def forcing(self, value):
        self._forcing = value


if __name__=='__main__':
    config= Config('config.txt')