from __future__ import division
import numpy as np
from scipy.stats import norm, gaussian_kde, rankdata
from ..util import read_param_file
import matplotlib.pyplot as plt

# Perform Delta moment-independent Analysis on file of model results
# Returns a dictionary with keys 'delta', 'delta_conf', 'S1', and 'S1_conf'
# Where each entry is a list of size D (the number of parameters)
# Containing the indices in the same order as the parameter file

def analyze(pfile, input_file, output_file, column=0, num_resamples=10,
            delim=' ', conf_level=0.95, plot=True):

    param_file = read_param_file(pfile)
    Y = np.loadtxt(output_file, delimiter=delim, usecols=(column,))
    X = np.loadtxt(input_file, delimiter=delim, ndmin=2)
    if len(X.shape) == 1:
        X = X.reshape((len(X), 1))

    D = param_file['num_vars']
    N = Y.size

    if conf_level < 0 or conf_level > 1:
        raise RuntimeError("Confidence level must be between 0-1.")

    # equal frequency partition
    M = min(np.ceil(N ** (2 / (7 + np.tanh((1500 - N) / 500)))), 48)
    m = np.linspace(0, N, M + 1)
    Ygrid = np.linspace(np.min(Y), np.max(Y), 100)

    keys = ('delta_mean', 'delta_std', 'delta_conf')
    S = dict((k, np.zeros(D)) for k in keys)
    print("Parameter %s %s %s" % keys)

    delta = np.empty([num_resamples, D])
    for i in range(D):
        delta[:,i] = bias_reduced_delta(
            Y, Ygrid, X[:, i], m, num_resamples, conf_level)  
        S['delta_mean'][i] = np.mean(delta[:,i])
        S['delta_std'][i] = np.std(delta[:,i])
        S['delta_conf'][i] = norm.ppf(0.5 + conf_level / 2) * delta[:,i].std(ddof=1)
        # S['S1'][i] = sobol_first(Y, X[:, i], m)
        # S['S1_conf'][i] = sobol_first_conf(
            # Y, X[:, i], m, num_resamples, conf_level)
        print("%s %f %f %f" % (param_file['names'][i], S['delta_mean'][
              i], S['delta_std'][i], S['delta_conf'][i]))
#        if S['delta'][i] < 0:  S['delta'][i] = 0
        
    if plot:
        fig=plt.figure()
        ax1=plt.subplot(121)
        for i in range(D):
            plt.plot(S['delta_mean'][i], S['delta_std'][i], 'ro')
            plt.text(S['delta_mean'][i], S['delta_std'][i], '%s' % param_file['names'][i])
        plt.title('Delta Test SA results') 
        plt.xlabel('Mean of Delta')       
        plt.ylabel('Std of Delta')
        ax1=plt.subplot(122)
        ax1.boxplot(delta)
        ax1.set_xticks(np.arange(param_file['num_vars'])+1)
        ax1.set_xticklabels(param_file['names'])
        plt.title('Delta Confidence Interval')
        plt.show()  
        
    return S

# Plischke et al. 2013 estimator (eqn 26) for d_hat

def calc_delta(Y, Ygrid, X, m):
    N = len(Y)
    fy = gaussian_kde(Y, bw_method='silverman')(Ygrid)
    xr = rankdata(X, method='ordinal')

    d_hat = 0
    for j in range(len(m) - 1):
        ix = np.where((xr > m[j]) & (xr <= m[j + 1]))[0]
        nm = len(ix)
        fyc = gaussian_kde(Y[ix], bw_method='silverman')(Ygrid)
        d_hat += (float(nm) / (2 * N)) * np.trapz(np.abs(fy - fyc), Ygrid)

    return d_hat

# Plischke et al. 2013 bias reduction technique (eqn 30)

def bias_reduced_delta(Y, Ygrid, X, m, num_resamples, conf_level):
    d = np.empty(num_resamples)
    d_hat = calc_delta(Y, Ygrid, X, m)

    for i in range(num_resamples):
        r = np.random.randint(len(Y), size=len(Y))
        d[i] = calc_delta(Y[r], Ygrid, X[r], m)

    d = 2 * d_hat - d
    return d
#    return (d.mean(), norm.ppf(0.5 + conf_level / 2) * d.std(ddof=1))


def sobol_first(Y, X, m):
    xr = rankdata(X, method='ordinal')
    Vi = 0
    N = len(Y)
    for j in range(len(m) - 1):
        ix = np.where((xr > m[j]) & (xr <= m[j + 1]))[0]
        nm = len(ix)
        Vi += (float(nm) / N) * (Y[ix].mean() - Y.mean()) ** 2
    return Vi / np.var(Y)


def sobol_first_conf(Y, X, m, num_resamples, conf_level):
    s = np.empty(num_resamples)

    for i in range(num_resamples):
        r = np.random.randint(len(Y), size=len(Y))
        s[i] = sobol_first(Y[r], X[r], m)

    return norm.ppf(0.5 + conf_level / 2) * s.std(ddof=1)