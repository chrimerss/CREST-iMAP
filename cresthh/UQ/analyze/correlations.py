from __future__ import division
from ..util import read_param_file
import numpy as np
import scipy.stats
import matplotlib.pyplot as plt

# Perform Correlation Analysis on file of model results
def analyze(pfile, input_file, output_file, column = 0, delim = ' ', plot = True):

    param_file = read_param_file(pfile)    
    X = np.loadtxt(input_file, delimiter = delim)
    Y = np.loadtxt(output_file, delimiter = delim)
    
    if len(X.shape) == 1: X = X.reshape((len(X),1))
    if len(Y.shape) == 1: Y = Y.reshape((len(Y),1))
    
    if Y.ndim > 1:
        Y = Y[:, column]
    
    # Pearson correlation, and two types of rank correlation (Spearman, Kendall)
    pearson = np.zeros(X.shape[1])
    spearman = np.zeros(X.shape[1])
    kendall = np.zeros(X.shape[1])
    
    for i in range(X.shape[1]):
        pearson[i], _ = scipy.stats.pearsonr(X[:,i], Y)
        spearman[i], _ = scipy.stats.spearmanr(X[:,i], Y)
        kendall[i], _ = scipy.stats.kendalltau(X[:,i], Y)
        print "For input parameter: ", param_file['names'][i]
        print "Pearson correlation coefficient:", pearson[i]
        print "Spearman correlation coefficient:", spearman[i]
        print "Kendall correlation coefficient:", kendall[i]
        
    if plot:
        plt.figure()
        ax = plt.subplot(221)
        plt.bar(np.arange(param_file['num_vars']), pearson, color='r')
        ax.set_xticks(np.arange(param_file['num_vars'])+0.4)
        ax.set_xticklabels(param_file['names'])
        plt.title('Pearson Correlation Coefficient Analysis')

        ax = plt.subplot(222)
        plt.bar(np.arange(param_file['num_vars']), spearman, color='y')
        ax.set_xticks(np.arange(param_file['num_vars'])+0.4)
        ax.set_xticklabels(param_file['names'])
        plt.title('Spearman Correlation Coefficient Analysis')
        
        ax = plt.subplot(223)
        plt.bar(np.arange(param_file['num_vars']), kendall, color='g')
        ax.set_xticks(np.arange(param_file['num_vars'])+0.4)
        ax.set_xticklabels(param_file['names'])
        plt.title('Kendall Correlation Coefficient Analysis')
        plt.show()