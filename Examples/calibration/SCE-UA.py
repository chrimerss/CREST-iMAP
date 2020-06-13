
import sys
sys.path.append('/home/ZhiLi/CRESTHH')
import cresthh
from cresthh import UQ
from cresthh.UQ.optimization import SCE

from cresthh.UQ.DoE import morris_oat
from cresthh.UQ.util import scale_samples_general, read_param_file, discrepancy
import shutil
import numpy as np

# Read in parameter file
param_file = 'params.txt'
pf= read_param_file(param_file)

# param_values= morris_oat.sample(10, pf['num_vars'], num_levels=4, grid_jump=2)
# scale_samples_general(param_values, pf['bounds'])

# np.savetxt('Input_params.txt', param_values, delimiter=' ')

shutil.copy('model.py', '/home/ZhiLi/CRESTHH/cresthh/UQ/test_functions/functn.py')
bl=np.empty(0)
bu=np.empty(0)
for i, b in enumerate(pf['bounds']):
    bl = np.append(bl, b[0])
    bu = np.append(bu, b[1])

SCE.sceua(bl, bu, pf, ngs=2)
# def 