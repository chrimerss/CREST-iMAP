from __future__ import division
import numpy as np
from . import sobol
from ..util import scale_samples, read_param_file
import matplotlib.pyplot as plt

# Generate matrix of samples for derivative-based global sensitivity measure (dgsm)
# start from a QMC (sobol) sequence and finite difference with delta % steps
def sample(N, param_file, delta=0.01, plot=True):

    pf = read_param_file(param_file)
    D = pf['num_vars']

    # How many values of the Sobol sequence to skip
    skip_values = 1000

    # Create base sequence - could be any type of sampling
    base_sequence = sobol.sample(N + skip_values, D, plot=False)
    # scale before finite differencing
    scale_samples(base_sequence, pf['bounds'])
    dgsm_sequence = np.empty([N * (D + 1), D])

    index = 0

    for i in range(skip_values, N + skip_values):

        # Copy the initial point
        dgsm_sequence[index, :] = base_sequence[i,:]
        index += 1

        for j in range(D):
            temp = np.zeros(D)
            temp[j] = base_sequence[i, j] * delta
            dgsm_sequence[index, :] = base_sequence[i,:] + temp
            dgsm_sequence[index, j] = min(
                dgsm_sequence[index, j], pf['bounds'][j][1])
            dgsm_sequence[index, j] = max(
                dgsm_sequence[index, j], pf['bounds'][j][0])
            index += 1
    if plot:
        plt.figure()
        ax = plt.subplot()
        plt.scatter(dgsm_sequence[:,0], dgsm_sequence[:,1])
        ax.set_xlim(pf['bounds'][0][0], pf['bounds'][0][1])
        ax.set_ylim(pf['bounds'][1][0], pf['bounds'][1][1])
        plt.title('Finite Difference Sampling')
        plt.show()
		
    return dgsm_sequence