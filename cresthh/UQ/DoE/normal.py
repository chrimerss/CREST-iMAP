import numpy as np
import matplotlib.pyplot as plt

 # Generate N x D matrix of standard normal samples
def sample(N, D, plot = True):
    temp = np.random.standard_normal([N*D])
    result = np.reshape(temp, (N, D))
    if plot:
        plt.figure()
        ax = plt.subplot()
        plt.scatter(result[:,0], result[:,1])
        ax.set_xlim(0,1)
        ax.set_ylim(0,1)
        plt.title('Normal distribution Sampling')
        plt.show()
		
    return result