from __future__ import division
from ..util import read_param_file
from sys import exit
import numpy as np
from scipy.stats import norm
import math
import matplotlib.pyplot as plt

# Perform FAST Analysis on file of model results
def analyze(pfile, output_file, column = 0, M = 4, delim = ' ',
            num_resamples = 100, conf_level=0.95, plot = True):
    
    param_file = read_param_file(pfile)
    Y = np.loadtxt(output_file, delimiter = delim)

    if len(Y.shape) == 1: Y = Y.reshape((len(Y),1))

    D = param_file['num_vars']
    
    if Y.ndim > 1:
        Y = Y[:, column]
    
    if Y.size % (D) == 0:
        N = int(Y.size / D)
    else:
        print """
            Error: Number of samples in model output file must be a multiple of D, 
            where D is the number of parameters in your parameter file.
          """
        exit()
    
    # Recreate the vector omega used in the sampling
    omega = np.empty([D])
    omega[0] = math.floor((N - 1) / (2 * M))
    m = math.floor(omega[0] / (2 * M))
    
    if m >= (D-1):
        omega[1:] = np.floor(np.linspace(1, m, D-1)) 
    else:
        omega[1:] = np.arange(D-1) % m + 1
    
    # Calculate and Output the First and Total Order Values
    firstResults = np.empty(0)
    totalResults = np.empty(0)
#    first_conf = np.empty([num_resamples, D])
#    total_conf = np.empty([num_resamples, D])
    print "Parameter First Total"
    for i in range(D):
        l = range(i*N, (i+1)*N)
        first = compute_first_order(Y[l], N, M, omega[0])
        total = compute_total_order(Y[l], N, omega[0])
#        first_conf[:,i], total_conf[:,i] = compute_conf(Y[l], N, M, D, omega[0], num_resamples)
        firstResults = np.append(firstResults, first)
        totalResults = np.append(totalResults, total)       
#        print "%s %f %f %f %f" % (param_file['names'][i], first, total, norm.ppf(0.5 + conf_level / 2) * first_conf[i].std(ddof=1), norm.ppf(0.5 + conf_level / 2) * total_conf[i].std(ddof=1))
        print "%s %f %f" % (param_file['names'][i], first, total)
        
    if plot:
        fig=plt.figure()
        colors = ['yellowgreen', 'gold', 'lightskyblue', 'lightcoral', 'red', 'green', 'pink', 'blue']
        ax1=plt.subplot(121)
        ax1.pie(10*firstResults, labels=param_file['names'], colors = colors, autopct='%1.1f%%', shadow=True)
        plt.title('FAST First order SA results')       
        ax2=plt.subplot(122)
        ax2.pie(10*totalResults, labels=param_file['names'], colors = colors, autopct='%1.1f%%', shadow=True)
        plt.title('FAST Total order SA results')
        
       # fig=plt.figure()
       # ax1=plt.subplot(121)
       # ax1.boxplot(first_conf)
       # ax1.set_xticks(np.arange(param_file['num_vars'])+1)
       # ax1.set_xticklabels(param_file['names'])
       # plt.title('FAST First order SA confidence interval')
       # ax2=plt.subplot(122)
       # ax2.boxplot(total_conf)
       # ax2.set_xticks(np.arange(param_file['num_vars'])+1)
       # ax2.set_xticklabels(param_file['names'])
       # plt.title('FAST Total order SA confidence interval')
        plt.show()  
    
def compute_first_order(outputs, N, M, omega):
    f = np.fft.fft(outputs)
    Sp = np.power(np.absolute(f[range(1,int(N/2))]) / N, 2)
    V = 2*np.sum(Sp)
    D1 = 2*np.sum(Sp[list(np.arange(1,M)*int(omega) - 1)])
    return D1/V

def compute_total_order(outputs, N, omega):
    f = np.fft.fft(outputs)
    Sp = np.power(np.absolute(f[range(1,int(N/2))]) / N, 2)
    V = 2*np.sum(Sp)
    Dt = 2*sum(Sp[range(int(omega/2))])
    return (1 - Dt/V)

# def compute_conf(outputs, N, M, D, omega, num_resamples):
    # first_conf = np.empty([num_resamples])
    # total_conf = np.empty([num_resamples])
    # outputs_resample = np.empty([N,1])
    # for i in range(num_resamples):
        # for j in range(N):            
            # index = np.random.randint(0, N)
            # outputs_resample[j] = outputs[index]
            
        # first_conf[i] = compute_first_order(outputs_resample, N, M, omega)
        # total_conf[i] = compute_total_order(outputs_resample, N, omega)
    # return first_conf, total_conf