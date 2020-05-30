import sys
sys.path.append('..')

# from CREST.model import CREST
from grid import Grid
from config import Config

def get_grids():
    grids= Grid(DEMpath='../data/dem/DEM.tif')

    return grids

def get_params():
    params= Config('../config.txt')
    print('System parameters:'%(params.sys))
    print('Crest parameters:'%(params.crest))

def test_crest():
    crest_mode= CREST()

def main():
    # test config file parser
    get_params()

if __name__=='__main__':
    main()