from __future__ import division
from ..util import read_param_file
import numpy as np
import scipy.stats
import matplotlib.pyplot as plt

# Perform Moments Analysis on file of model results
def analyze(pfile, input_file, output_file, column = 0, delim = ' ', plot = True):

    param_file = read_param_file(pfile)  
    X = np.loadtxt(input_file, delimiter = delim)
    Y = np.loadtxt(output_file, delimiter = delim)
    
    if len(X.shape) == 1: X = X.reshape((len(X),1))
    if len(Y.shape) == 1: Y = Y.reshape((len(Y),1))
    
    if Y.ndim > 1:
        Y = Y[:, column]
    
    # two-sample t-test
    # null hypothesis: the two groups have the same mean
    # this test assumes the two groups have the same variance
    t_test = np.zeros(X.shape[1]); t_test_p = np.zeros(X.shape[1])
    for i in range(X.shape[1]):
        [t_test[i], t_test_p[i]] = scipy.stats.ttest_ind(X[:,i], Y)
        print "For input parameter: ", param_file['names'][i]
        print "Two sample t-test results:", t_test[i]
        print "Two sample t-test 2-tailed p-value:", t_test_p[i]
    
    if plot:
        plt.figure()
        ax1 = plt.subplot(221)
        plt.bar(np.arange(param_file['num_vars']), t_test_p, color='r')
        x = plt.gca().xaxis.get_ticklocs()
        y = x*0+0.05
        plt.plot(x, y, color='r', linewidth=6)
        ax1.set_xticks(np.arange(param_file['num_vars'])+0.4)
        ax1.set_xticklabels(param_file['names'])
        plt.title('T-test Results')
        
    # two-sample Kolmogorov-Smirnov test
    # null hypothesis: the two independent samples are drawn from the same continuous distribution
    # the distribution of sample is assumed to be continuous
    # If the K-S statistic is small or the p-value is high, we should reject the null hypothesis
    ks_test = np.zeros(X.shape[1]); ks_test_p = np.zeros(X.shape[1])
    for i in range(X.shape[1]):
        [ks_test[i], ks_test_p[i]] = scipy.stats.ks_2samp(X[:,i], Y)
        print "For input parameter: ", param_file['names'][i]
        print "Two sample Kolmogorov-Smirnov test results:", ks_test[i]
        print "Two sample Kolmogorov-Smirnov test 2-tailed p-value:", ks_test_p[i]
    
    if plot:
        ax2 = plt.subplot(222)
        plt.bar(np.arange(param_file['num_vars']), ks_test_p, color='g')
        x = plt.gca().xaxis.get_ticklocs()
        y = x*0+0.05
        plt.plot(x, y, color='g', linewidth=6)
        ax2.set_xticks(np.arange(param_file['num_vars'])+0.4)
        ax2.set_xticklabels(param_file['names'])
        plt.title('Kolmogorov-Smirnov test Results')

    # two-sample Wilcoxon rank-sum test
    # null hypothesis: the two independent samples are drawn from the same continuous distribution
    # alternative hypothesis: the values in one sample are more likely to be larger than the values in the other sample
    # the distribution of sample is assumed to be continuous
    # If the Wilcoxon statistic is small or the p-value is high, we should reject the null hypothesis
    rank_test = np.zeros(X.shape[1]); rank_test_p = np.zeros(X.shape[1])
    for i in range(X.shape[1]):
        [rank_test[i], rank_test_p[i]] = scipy.stats.ranksums(X[:,i], Y)
        print "For input parameter: ", param_file['names'][i]
        print "Two sample Wilcoxon rank-sum test results:", rank_test[i]
        print "Two sample Wilcoxon rank-sum test 2-tailed p-value:", rank_test_p[i]
    
    if plot:
        ax3 = plt.subplot(223)
        plt.bar(np.arange(param_file['num_vars']), rank_test_p, color='b')
        x = plt.gca().xaxis.get_ticklocs()
        y = x*0+0.05
        plt.plot(x, y, color='b', linewidth=6)
        ax3.set_xticks(np.arange(param_file['num_vars'])+0.4)
        ax3.set_xticklabels(param_file['names'])
        plt.title('Wilcoxon rank-sum test Results')
        plt.show()          