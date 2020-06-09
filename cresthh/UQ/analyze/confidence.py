from ..util import read_param_file
import os
import numpy as np
import scipy.stats
import matplotlib.pyplot as plt

# Perform Confidence Interval Analysis on file of model results
def analyze(output_file, column = 0, delim = ' '):
    
    Y = np.loadtxt(output_file, delimiter = delim)

    if len(Y.shape) == 1: Y = Y.reshape((len(Y),1))

    if Y.ndim > 1:
        Y = Y[:, column]
    
    # sigmas=(0.674, 0.95, 0.997)
    m, l1, h1 = mean_confidence_interval(Y, 0.674)
    _, l2, h2 = mean_confidence_interval(Y, 0.95)
    _, l3, h3 = mean_confidence_interval(Y, 0.997)
    print "Confidence Interval of output:"
    print " 99.70%   95.00%   67.40%  0.00%   67.40%   95.00%   99.70% "
    print " %.3f    %.3f    %.3f    %.2f    %.3f    %.3f    %.3f" %(l3, l2, l1, m, h1, h2, h3)
    os.system("pause")    
    
def mean_confidence_interval(data, confidence):
    a = 1.0*np.array(data)
    n = len(a)
    m, se = np.mean(a), scipy.stats.sem(a)
    h = se * scipy.stats.t.ppf((1+confidence)/2., n-1)
    return m, m-h, m+h