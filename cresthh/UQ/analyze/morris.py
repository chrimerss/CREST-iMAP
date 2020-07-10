from __future__ import division
from ..util import read_param_file
from sys import exit
import numpy as np
from scipy.stats import norm
import matplotlib.pyplot as plt

# Perform Morris Analysis on file of model results
def analyze(pfile, input_file, output_file, column = 0, delim = ' ', num_resamples = 1000, plot = True, **kwargs):
    
    param_file = read_param_file(pfile)
    Y = np.loadtxt(output_file, delimiter = delim)
    X = np.loadtxt(input_file, delimiter = delim)

    if len(Y.shape) == 1: Y = Y.reshape((len(Y),1))
    if len(X.shape) == 1: X = X.reshape((len(X),1))
    
    if Y.ndim > 1:
        Y = Y[:, column]
    
    D = param_file['num_vars']
    
    if Y.size % (D+1) == 0:    
        N = int(Y.size / (D + 1))
    else:
        print """
                Error: Number of samples in model output file must be a multiple of (D+1), 
                where D is the number of parameters in your parameter file.
              """
        exit()            
    
    ee = np.empty([N, D])
    
    # For each of the N trajectories
    for i in range(N):
        
        # Set up the indices corresponding to this trajectory
        j = np.arange(D+1) + i*(D + 1)
        j1 = j[0:D]
        j2 = j[1:D+1]
        
        # The elementary effect is (change in output)/(change in input)
        # Each parameter has one EE per trajectory, because it is only changed once in each trajectory
        ee[i,:] = np.linalg.solve((X[j2,:] - X[j1,:]), (Y[j2] - Y[j1])) 
    
    # Output the Mu, Mu*, and Sigma Values
    mu_star_x = np.empty(0)
    sigma_y = np.empty(0)
    mu_star_conf_z=np.empty([D,num_resamples])
    print "Parameter  Mu  Sigma  Mu_Star  Mu_Star_Conf"
    for j in range(D):
        mu = np.average(ee[:,j])
        mu_star = np.average(np.abs(ee[:,j]))
        sigma = np.std(ee[:,j])
        mu_star_conf = compute_mu_star_confidence(ee[:,j], N, num_resamples)
        
        mu_star_x = np.append(mu_star_x, mu_star)
        sigma_y = np.append(sigma_y, sigma)
        mu_star_conf_z[j,:] = mu_star_conf
        
        print "%s %f %f %f %f" % (param_file['names'][j], mu, sigma, mu_star, 1.96 * mu_star_conf.std(ddof=1))
        
    if plot:
        fig=plt.figure(**kwargs)
        ax1=plt.subplot(121)
        for i in range(D):
            plt.plot(mu_star_x[i], sigma_y[i], 'ro')
            plt.text(mu_star_x[i], sigma_y[i], '%s' % param_file['names'][i])
        plt.title('Morries One at A Time SA results') 
        plt.xlabel('Modified Means (of gradients)')       
        plt.ylabel('Standard Deviation (of gradients)')
        ax1=plt.subplot(122)
        mu_star_conf_z = mu_star_conf_z.T
        ax1.boxplot(mu_star_conf_z)
        ax1.set_xticks(np.arange(param_file['num_vars'])+1)
        ax1.set_xticklabels(param_file['names'])
        plt.title('Modified Means Plot(bootstrap)')
        plt.xlabel('Parameter Name')
        plt.ylabel('Modified Means (of gradients)')
        plt.show()
    
    return mu_star_x, sigma_y, mu_star_conf_z

def compute_mu_star_confidence(ee, N, num_resamples):
   
   ee_resampled = np.empty([N])
   mu_star_resampled  = np.empty([num_resamples])
   
   for i in range(num_resamples):
       for j in range(N):
           
           index = np.random.randint(0, N)
           ee_resampled[j] = ee[index]
       
       mu_star_resampled[i] = np.average(np.abs(ee_resampled))
   
   return mu_star_resampled