import numpy as np
import matplotlib.pyplot as plt
import _design as design

# Generate N x D matrix of Improved Distributed Hypercube samples
def sample(N, D, plot = True):
    seed = design.get_seed()
    sequence = design.ihs(D, N, seed=seed, duplication=5).T
    result = np.empty([N, D])
    
    for i in range(N):
        for j in range(D):
            result[i,j] = sequence[i][j]/float(N)
            
    if plot:
        plt.figure()
        ax = plt.subplot()
        plt.scatter(result[:,0], result[:,1])
        ax.set_xlim(0,1)
        ax.set_ylim(0,1)
        plt.title('Improved Distributed Hypercube Sequence Sampling')
        plt.show()
        
    return result