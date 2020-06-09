from __future__ import division
import numpy as np
import matplotlib.pyplot as plt

# Generate N x D matrix of symmetric latin hypercube samples
def sample(N, D, plot = True):
    
    delta = (1.0 / N) * np.ones(D)
    X = np.zeros([N, D])

    for j in range(D):
        for i in range(N):
            X[i, j] = ((2.0 * (i + 1) - 1) / 2.0) * delta[j]
    P = np.zeros([N, D], dtype = int);

    P[:, 0] = np.arange(N)
    if N % 2 == 0:
        k = N / 2
    else:
        k = (N - 1) / 2	
        P[k, :] = (k + 1) * np.ones((1, D))

    for j in range(1, D):
        P[0:k, j] = np.random.permutation(np.arange(k))
        for i in range(int(k)):
            if np.random.random() < 0.5:
                P[N - 1 - i, j] = N - 1 - P[i, j]
            else:
                P[N - 1 - i, j] = P[i, j]
                P[i, j] = N - 1 - P[i, j]   
    
	result = np.zeros([N, D])
	
    for j in range(D):
        for i in range(N):
            result[i, j] = X[P[i, j], j]

    if plot:
        plt.figure()
        ax = plt.subplot()
        plt.scatter(result[:,0], result[:,1])
        ax.set_xlim(0,1)
        ax.set_ylim(0,1)
        plt.title('Symmetric Latin Hypercube Sampling')
        plt.show()
			
    return result