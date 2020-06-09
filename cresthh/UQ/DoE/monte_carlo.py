import numpy as np
import matplotlib.pyplot as plt

# Generate N x D matrix of uniform [0, 1] samples
def sample(N, D, plot = True):
    result = np.random.random([N, D])
    if plot:
        plt.figure()
        ax = plt.subplot()
        plt.scatter(result[:,0], result[:,1])
        ax.set_xlim(0,1)
        ax.set_ylim(0,1)
        plt.title('Monte Carlo Sampling')
        plt.show()
        
    return result