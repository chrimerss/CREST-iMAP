from ..DoE import monte_carlo
import numpy as np
from ..test_functions import functn

def optimization(bl, bu, pf, max_sample = 100):
    
    fraction = 0.2
    dim = pf['num_vars']
    bestx = monte_carlo.sample(1, dim, plot = False)
    bestf = functn.evaluate(bestx)[0]
    
    samples = np.empty([max_sample, dim])
    values = np.empty(0)
    bestValues = np.empty(0)
    
    # Begin local search
    for i in range(max_sample):
        Pn = 1.0-np.log(i+1)/np.log(max_sample)
        count = 0
        testx = bestx
        randnums = np.random.rand(dim,1)
        for j in range(dim):
            if randnums[j] < Pn:
                count = count + 1
                testx[0][j] = neigh_value(testx[0][j],bl[j],bu[j],fraction)
                
        if count == 0:
            dec_var = np.ceil(dim * np.random.rand(1,1))
            dec_var = int(dec_var[0][0] - 1)
            testx[0][dec_var] = neigh_value(testx[0][dec_var],bl[dec_var],bu[dec_var],fraction)
            
        # Get objective function value      
        testf = functn.evaluate(testx)[0]
        
        if testf <= bestf:
            bestf = testf
            bestx = testx

        print "The best function value for now is: "+str(bestf)
        samples[i,:] = samples[0]
        values = np.append(values, testf)
        bestValues = np.append(bestValues, bestf)

    np.savetxt('Samples_DDS.txt', samples, delimiter=' ')
    np.savetxt('Values_DDS.txt', values, delimiter=' ')
    np.savetxt('BestValues_DDS.txt', bestValues, delimiter=' ')
    
    
def neigh_value(s, bl, bu, fraction):

    range = bu - bl
    snew = s + np.random.rand(1,1) * fraction * range
    
    # Deal with variable upper and lower bounds:
    if snew < bl:
        snew = bl + (bl - snew)
        if snew > bu:
            snew = bl       
    elif snew > bu:
        snew = bu - (snew - bu)
        if snew < bl:
            snew = bu
            
    return snew