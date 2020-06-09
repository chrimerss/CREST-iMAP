from sys import exit
import argparse, shutil
import numpy as np
from ..util import read_param_file, scale_samples

parser = argparse.ArgumentParser(description='Perform parameter optimization on model')

parser.add_argument('-m', '--method', type=str, choices=['sce', 'dds', 'ASMO', 'mcmc', 'PSO', 'GA', 'SA'], required=True)
parser.add_argument('-p', '--paramfile', type=str, required=True)
parser.add_argument('-f', '--modelfile', type=str, required=True)
args = parser.parse_args()

bl=np.empty(0)
bu=np.empty(0)
pf = read_param_file(args.paramfile)
for i, b in enumerate(pf['bounds']):
    bl = np.append(bl, b[0])
    bu = np.append(bu, b[1])

dir = './UQ/test_functions/'
shutil.copy(args.modelfile, dir+'functn.py')

import SCE, PSO, ASMO, DDS

if args.method == 'sce':
    SCE.sceua(bl, bu, pf, ngs=2)
elif args.method == 'dds':
    DDS.optimization(bl, bu, pf, max_sample = 100)
elif args.method == 'ASMO':
    ASMO.optimization(bl, bu, pf, max_sample = 100)
# elif args.method == 'mcmc':
    # MCMC.optimization(bl, bu, pf)
elif args.method == 'PSO':
    PSO.optimization(bl, bu, pf)
# elif args.method == 'GA':
    # GA.method(bl, bu)
# elif args.method == 'SA':
    # SA.method(bl, bu)	