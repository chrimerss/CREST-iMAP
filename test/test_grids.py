import sys
sys.path.append('..')
from grid import Grid

def main():
    grid= Grid(DEMpath='../data/dem/DEM.tif')


if __name__ == '__main__':
    main()