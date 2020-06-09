from __future__ import division
from ..util import read_param_file
import numpy as np
import scipy.stats
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# Perform Moments Analysis on file of model results
def analyze(output_file, column = 0, delim = ' ', plot = True):
    
    Y = np.loadtxt(output_file, delimiter = delim)

    if len(Y.shape) == 1: Y = Y.reshape((len(Y),1))

    if Y.ndim > 1:
        Y = Y[:, column]
    
    # Output the mean and variance value
    print "The minimum value of output is: ", Y.min()
    print "The maximum value of output is: ", Y.max()
    print "The mean value (first moment) is: ", Y.mean()
    print "The variance value (second moment) is:", Y.var()
    print "The standard deviation is: ", Y.std()
    print "The skewness value (third moment) is: ", scipy.stats.skew(Y)
    print "The kurtosis value (fourth moment) is: ", scipy.stats.kurtosis(Y)
    
    if plot:
        plt.figure()
        plt.hist(Y, bins=50)
        plt.xlabel('Model Evaluation Value')
        plt.ylabel('Number of Evaluations')
        plt.title('Hist Figure of Model Evaluation Results')
        plt.show()
    