import numpy as np
import matplotlib.pyplot as plt
import _design as design

# Generate N x D matrix of QMC faure samples
def sample(N, D, plot = True):
    sequence = design.faure_generate(D, N).T
    result = np.empty([N, D])
    
    for i in range(N):
        for j in range(D):
            result[i,j] = sequence[i][j]
            
    if plot:
        plt.figure()
        ax = plt.subplot()
        plt.scatter(result[:,0], result[:,1])
        ax.set_xlim(0,1)
        ax.set_ylim(0,1)
        plt.title('QMC Faure Sampling')
        plt.show()
        
    return result