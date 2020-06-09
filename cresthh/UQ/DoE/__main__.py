import os
import numpy as np
import random as rd
import matplotlib.pyplot as plt
import argparse, shutil, time, datetime
from ..util import read_param_file, scale_samples, scale_samples_general, discrepancy
from . import monte_carlo, normal, sobol, lhs, box_behnken, central_composite, fast_sampler,\
ff2n, finite_diff, frac_fact, full_fact, morris_oat, plackett_burman, saltelli, symmetric_LH

parser = argparse.ArgumentParser(description='Create parameter samples for sensitivity/uncertainty/regression analysis')

parser.add_argument('-m', '--method', type=str, choices=['mc', 'normal', 'sobol', 'halton', 'faure', 'hammersley',\
'latin1', 'latin2', 'latin3', 'latin4', 'latin5', 'SLH', 'ihs', 'GLP',\
'CC', 'F1', 'F2', 'GP', 'GL', 'GH', 'LG',\
'full', 'ff2n', 'frac', 'box', 'central', 'plackett', 'finite_diff', 'saltelli', 'morris', 'fast'], required=True)
parser.add_argument('-n', '--samples', type=int, required=False, help='Number of Samples')
parser.add_argument('-f', '--factors', type=int, required=False, help='Number of Factors')
parser.add_argument('-a', '--maxLevel', type=int, required=False, help='The Maximum level of the grid')
parser.add_argument('-p', '--paramfile', type=str, required=False, help='Parameter Range File')
parser.add_argument('-d', '--driver', type=str, required=False, help='Driver of Model')
parser.add_argument('-l', '--levels', type=str, required=False, help='Levels of Full-Factorial design')
parser.add_argument('-g', '--generator', type=str, required=False, help='Generator string of Fractional-Factorial design')
parser.add_argument('-s', '--seed', type=int, required=False, default=1, help='Random Seed')
parser.add_argument('--delimiter', type=str, required=False, default=' ', help='Column delimiter')
parser.add_argument('--precision', type=int, required=False, default=8, help='Output floating-point precision')
parser.add_argument('--saltelli-max-order', type=int, required=False, default=2, choices=[1, 2], help='Maximum order of sensitivity indices to calculate (Saltelli only)')
parser.add_argument('--morris-num-levels', type=int, required=False, default=4, help='Number of grid levels (Morris only)')
parser.add_argument('--morris-grid-jump', type=int, required=False, default=2, help='Grid jump size (Morris only)')
parser.add_argument('-t', '--delta', type=float, required=False, default=0.01, help='Finite difference step size (percent)')
args = parser.parse_args()

np.random.seed(args.seed)
rd.seed(args.seed)
pf = read_param_file(args.paramfile)

if args.method == 'mc':
    param_values = monte_carlo.sample(args.samples, pf['num_vars'])
elif args.method == 'normal':
    param_values = normal.sample(args.samples, pf['num_vars'])
elif args.method == 'sobol':
    param_values = sobol.sample(args.samples, pf['num_vars'])
elif args.method == 'halton':
    param_values = halton.sample(args.samples, pf['num_vars'])
elif args.method == 'faure':
    param_values = faure.sample(args.samples, pf['num_vars'])
elif args.method == 'hammersley':
    param_values = hammersley.sample(args.samples, pf['num_vars'])
elif args.method == 'latin1':
    param_values = lhs.sample(args.samples, pf['num_vars'])
elif args.method == 'latin2':
    param_values = lhs.sample(args.samples, pf['num_vars'], criterion='center')
elif args.method == 'latin3':
    param_values = lhs.sample(args.samples, pf['num_vars'], criterion='maximin')
elif args.method == 'latin4':
    param_values = lhs.sample(args.samples, pf['num_vars'], criterion='centermaximin')
elif args.method == 'latin5':
    param_values = lhs.sample(args.samples, pf['num_vars'], criterion='correlation')
elif args.method == 'SLH':
    param_values = symmetric_LH.sample(args.samples, pf['num_vars'])
elif args.method == 'ihs':
    param_values = ihs.sample(args.samples, pf['num_vars'])
elif args.method == 'GLP':
    param_values = GLP.sample(args.samples, pf['num_vars'])
elif args.method == 'saltelli':
    calc_second_order = (args.saltelli_max_order == 2)
    param_values = saltelli.sample(args.samples, pf['num_vars'], calc_second_order)
elif args.method == 'morris':
    param_values = morris_oat.sample(args.samples, pf['num_vars'], args.morris_num_levels, args.morris_grid_jump)
elif args.method == 'fast':
    param_values = fast_sampler.sample(args.samples, pf['num_vars'])
elif args.method == 'finite_diff':
    param_values = finite_diff.sample(args.samples, args.paramfile, args.delta)
elif args.method == 'full':
    arr = args.levels.split(' ')
    arr = [int(arr) for arr in arr if arr]
    param_values = full_fact.sample(arr)
elif args.method == 'ff2n':
#    param_values = ff2n.sample(args.factors)
    param_values = ff2n.sample(pf['num_vars'])
elif args.method == 'frac':
    param_values = frac_fact.sample(args.generator)
elif args.method == 'box':
#    param_values = box_behnken.sample(args.factors)
    param_values = box_behnken.sample(pf['num_vars'])
elif args.method == 'central':
#    param_values = central_composite.sample(args.factors)
    param_values = central_composite.sample(pf['num_vars'])
elif args.method == 'plackett':
#    param_values = plackett_burman.sample(args.factors)
    param_values = plackett_burman.sample(pf['num_vars'])
elif args.method == 'CC':
    param_values = CC.sample(pf['num_vars'], args.maxLevel)
    print param_values
elif args.method == 'F1':
    param_values = F1.sample(pf['num_vars'], args.maxLevel)
elif args.method == 'F2':
    param_values = F2.sample(pf['num_vars'], args.maxLevel)
elif args.method == 'GP':
    param_values = GP.sample(pf['num_vars'], args.maxLevel)
elif args.method == 'GL':
    param_values = GL.sample(pf['num_vars'], args.maxLevel)
elif args.method == 'GH':
    param_values = GH.sample(pf['num_vars'], args.maxLevel)
elif args.method == 'LG':
    param_values = LG.sample(pf['num_vars'], args.maxLevel)
    
if (args.method == 'mc' or args.method == 'normal' or args.method == 'sobol' or args.method =='halton' or args.method == 'faure' or args.method == 'hammersley' \
or args.method == 'latin1' or args.method == 'latin2' or args.method == 'latin3' or args.method == 'latin4' or args.method == 'latin5' or args.method == 'SLH' \
or args.method == 'ihs' or args.method == 'GLP') and args.samples <= 200:
    print "Calculate the discrepancy evaluation results..."
    discrepancy.evaluate(param_values)

scale_samples_general(param_values, pf['bounds'])
dir = './UQ/test_functions/'
shutil.copy(args.driver, dir+'functn.py')

from ..test_functions import functn
model_values = functn.evaluate(param_values)

# Note: for tab-delimited file, enter $'\t' as the delimiter argument on the command line
# Otherwise Bash might mess up the escape characters
np.savetxt('sample_output_'+args.method+'_'+str(datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S'))+'.txt', param_values, delimiter=args.delimiter, fmt='%.' + str(args.precision) + 'e')
np.savetxt('model_output_'+args.method+'_'+str(datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S'))+'.txt', model_values, delimiter=args.delimiter, fmt='%.' + str(args.precision) + 'e')
    
lens = len(model_values)
plt.figure()
ax = plt.subplot()
plt.scatter(np.linspace(1,lens,num=lens), model_values)
ax.set_xlim(0,lens)
ax.set_ylim(model_values.min(),model_values.max())
plt.xlabel('Sample Number')
plt.ylabel('Model Evaluation Results')
plt.title('Model Evaluation Results')
plt.show()