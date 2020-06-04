import sys
import pandas as pd
sys.path.append('..')

from CREST.model import CREST
from grid import Grid
from config import Config
import time
import numpy as np

def get_grids(param):
    grids= Grid(crest_param=param.crest,DEMpath='../data/dem/DEM.tif', )

    return grids

def get_params():
    params= Config('/home/ZhiLi/CRESTHH/config.txt')
    # print('System parameters:%s'%(params.sys))
    # print('Crest parameters:%s'%(params.crest))
    # print('Forcing folders:%s'%(params.forcing))

    return params

def test_crest(grids, params):
    crest_model= CREST(grids, params)
    start=params.sys['start']
    end= params.sys['end']
    periods= pd.date_range(start, end, freq=params.sys['TimeStep'])
    for date in periods:
        states, fluxes= crest_model.step(date)
        # np.save('temp_checking/%s_states_fluxes.npy'%date.strftime('%Y%m%d%H%M'), np.concatenate([states['SI0'], fluxes['RI']]))
        # print()
        crest_model.write_GTIF('temp_checking/%s_RS.tif'%date.strftime('%Y%m%d%H%M'), fluxes['RS']+fluxes['RI'])


def main():
    # test config file parser
    params= get_params()
    grids= get_grids(params)
    test_crest(grids, params)

if __name__=='__main__':
    main()