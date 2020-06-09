from __future__ import division
from ..util import scale_samples
from ..DoE import lhs
from ..RSmodel import gp
from ..test_functions import functn
import numpy as np
import os, random

# Perform ASMO Optimization Analysis on model
def optimization(bl, bu, pf, max_sample = 35):
    
    dim = len(bl)
    bounds = pf["bounds"]
    initial_sample = 2 * (dim + 1)
    param_values = lhs.sample(initial_sample, dim, criterion='center', plot=False)
    
    for i, b in enumerate(bounds):
        param_values[:,i] = param_values[:,i] * (b[1] - b[0]) + b[0]    

    np.savetxt('initial_Input.txt', param_values, delimiter=' ')
    
    Y = functn.evaluate(param_values)
    np.savetxt('initial_Output.txt', Y, delimiter=' ')

    bestValue = Y.min()
    
    for i in range(max_sample - initial_sample):
    
        np.savetxt('Input_tmp.txt', param_values, delimiter=' ')
        np.savetxt('Output_tmp.txt', Y, delimiter=' ')
        
        print "Building GP surrogate model...\n"
        model = gp.regression('Input_tmp.txt', 'Output_tmp.txt', column = 0, cv = False)

        print "Begin SCE-UA global optimization algorithm...\n"
        bestx = SampleInputMatrix(1,dim,bu,bl,0,distname='randomUniform') 
        bestx[0] = sceua(bl, bu, 2, model)
        bestf = functn.evaluate(bestx)[0]
        
        param_values = np.append(param_values, bestx, axis=0)
        Y = np.append(Y, bestf)
        bestValue = np.append(bestValue, Y.min())

        print "Adaptive sample point x value: \n"
        print bestx
        print "Adaptive sample function value: " + str(bestf)
        print "Best function value for now: " + str(Y.min())


    # Save final results    
    np.savetxt('Input.txt', param_values, delimiter=' ')
    np.savetxt('Output.txt', Y, delimiter=' ')  
    np.savetxt('bestValue.txt', bestValue, delimiter=' ')   
    os.remove('Input_tmp.txt')
    os.remove('Output_tmp.txt')
    
    
def SampleInputMatrix(nrows,npars,bu,bl,iseed,distname='randomUniform'):
    '''
    Create input parameter matrix for nrows simulations,
    for npars with bounds ub and lb (np.array from same size)
    distname gives the initial sampling distribution (currently one for all parameters)

    returns np.array
    '''
    np.random.seed(iseed)
    x = np.zeros((nrows,npars))
    bound = bu - bl
    for i in range(nrows):
        x[i,:] = bl + np.random.rand(1,npars)*bound
    return x

def cceua(s,sf,bl,bu,model,icall,iseed):
    #  This is the subroutine for generating a new point in a simplex
    nps,nopt=s.shape
    n = nps
    m = nopt
    alpha = 1.0
    beta = 0.5

    # Assign the best and worst points:
    sb=s[0,:]
    fb=sf[0]
    sw=s[-1,:]
    fw=sf[-1]

    # Compute the centroid of the simplex excluding the worst point:
    ce= np.mean(s[:-1,:],axis=0)

    # Attempt a reflection point
    snew = SampleInputMatrix(1,nopt,bu,bl,iseed,distname='randomUniform')
    snew[0] = ce + alpha*(ce-sw)

    # Check if is outside the bounds:
    ibound=0
    s1=snew[0]-bl
    idx=(s1<0).nonzero()
    if idx[0].size <> 0:
        ibound=1

    s1=bu-snew[0]
    idx=(s1<0).nonzero()
    if idx[0].size <> 0:
        ibound=2

    if ibound >= 1:
        snew = SampleInputMatrix(1,nopt,bu,bl,iseed,distname='randomUniform')

    fnew = model.predict(snew)[0]
    icall += 1

    # Reflection failed; now attempt a contraction point:
    if fnew > fw:
        snew[0] = sw + beta * (ce-sw)
        fnew = model.predict(snew)[0]
        icall += 1

    # Both reflection and contraction have failed, attempt a random point;
        if fnew > fw:
            snew = SampleInputMatrix(1,nopt,bu,bl,iseed,distname='randomUniform')
            fnew = model.predict(snew)[0]
            icall += 1

    # END OF CCE
    return snew[0],fnew,icall


def sceua(bl,bu,ngs,model):
# This is the subroutine implementing the SCE algorithm,
# written by Q.Duan, 9/2004 - converted to python by Van Hoey S.2011

    # Initialize SCE parameters:
    nopt=len(bl)
    npg=2*nopt+1
    nps=nopt+1
    nspl=npg
    npt=npg*ngs
    bound=bu-bl
    maxn=10000
    kstop=10
    pcento=0.1
    peps=0.001
    iseed=0
    iniflg=0
    ngs=2

    # Create an initial population to fill array x(npt,nopt):
    x = SampleInputMatrix(npt,nopt,bu,bl,iseed,distname='randomUniform')
    if iniflg==1:
        x[0,:]=x0

    nloop=0
    icall=0
    xf=np.zeros(npt)
    xf=model.predict(x)
    for i in range(npt):
        icall += 1
    f0=xf[0]

    # Sort the population in order of increasing function values;
    idx = np.argsort(xf)
    xf = np.sort(xf)
    x=x[idx,:]

    # Record the best and worst points;
    bestx=x[0,:]
    bestf=xf[0]
    worstx=x[-1,:]
    worstf=xf[-1]

    BESTF=bestf
    BESTX=bestx
    ICALL=icall

    # Compute the standard deviation for each parameter
    xnstd=np.std(x,axis=0)

    # Computes the normalized geometric range of the parameters
    gnrng=np.exp(np.mean(np.log((np.max(x,axis=0)-np.min(x,axis=0))/bound)))

    # Check for convergency;
    if icall >= maxn:
        print '*** OPTIMIZATION SEARCH TERMINATED BECAUSE THE LIMIT'
        print 'ON THE MAXIMUM NUMBER OF TRIALS '
        print maxn
        print 'HAS BEEN EXCEEDED.  SEARCH WAS STOPPED AT TRIAL NUMBER:'
        print icall
        print 'OF THE INITIAL LOOP!'

    if gnrng < peps:
        print 'THE POPULATION HAS CONVERGED TO A PRESPECIFIED SMALL PARAMETER SPACE'

    # Begin evolution loops:
    nloop = 0
    criter=[]
    criter_change=1e+5

    while icall<maxn and gnrng>peps and criter_change>pcento:
        nloop+=1

        # Loop on complexes (sub-populations);
        for igs in range(ngs):
            # Partition the population into complexes (sub-populations);
            cx=np.zeros((npg,nopt))
            cf=np.zeros((npg))

            k1=np.array(range(npg))
            k2=k1*ngs+igs
            cx[k1,:] = x[k2,:]
            cf[k1] = xf[k2]

            # Evolve sub-population igs for nspl steps:
            for loop in range(nspl):

                # Select simplex by sampling the complex according to a linear
                # probability distribution
                lcs=np.array([0]*nps)
                lcs[0] = 1
                for k3 in range(1,nps):
                    for i in range(1000):
                        lpos = int(np.floor(npg+0.5-np.sqrt((npg+0.5)**2 - npg*(npg+1)*random.random())))
                        idx=(lcs[0:k3]==lpos).nonzero()
                        if idx[0].size == 0:
                            break

                    lcs[k3] = lpos
                lcs.sort()

                # Construct the simplex:
                s = np.zeros((nps,nopt))
                s=cx[lcs,:]
                sf = cf[lcs]

                snew,fnew,icall=cceua(s,sf,bl,bu,model,icall,iseed)

                # Replace the worst point in Simplex with the new point:
                s[-1,:] = snew
                sf[-1] = fnew

                # Replace the simplex into the complex;
                cx[lcs,:] = s
                cf[lcs] = sf

                # Sort the complex;
                idx = np.argsort(cf)
                cf = np.sort(cf)
                cx=cx[idx,:]

            # End of Inner Loop for Competitive Evolution of Simplexes
            # End of Evolve sub-population igs for nspl steps:

            # Replace the complex back into the population;
            x[k2,:] = cx[k1,:]
            xf[k2] = cf[k1]

        # End of Loop on Complex Evolution;

        # Shuffled the complexes;
        idx = np.argsort(xf)
        xf = np.sort(xf)
        x=x[idx,:]

        PX=x
        PF=xf

        # Record the best and worst points;
        bestx=x[0,:]
        bestf=xf[0]
        worstx=x[-1,:]
        worstf=xf[-1]

        BESTX = np.append(BESTX,bestx, axis=0)
        BESTF = np.append(BESTF,bestf)
        ICALL = np.append(ICALL,icall)

        # Compute the standard deviation for each parameter
        xnstd=np.std(x,axis=0)

        # Computes the normalized geometric range of the parameters
        gnrng=np.exp(np.mean(np.log((np.max(x,axis=0)-np.min(x,axis=0))/bound)))

        # Check for convergency;
        if icall >= maxn:
            print '*** OPTIMIZATION SEARCH TERMINATED BECAUSE THE LIMIT'
            print 'ON THE MAXIMUM NUMBER OF TRIALS '
            print maxn
            print 'HAS BEEN EXCEEDED.'

        if gnrng < peps:
            print 'THE POPULATION HAS CONVERGED TO A PRESPECIFIED SMALL PARAMETER SPACE'

        criter=np.append(criter,bestf)

        if nloop >= kstop:
            criter_change= np.abs(criter[nloop-1]-criter[nloop-kstop])*100
            criter_change= criter_change/np.mean(np.abs(criter[nloop-kstop:nloop]))
            if criter_change < pcento:
                print 'THE BEST POINT HAS IMPROVED IN LAST %d LOOPS BY LESS THAN THE THRESHOLD %f' %(kstop,pcento)
                print 'CONVERGENCY HAS ACHIEVED BASED ON OBJECTIVE FUNCTION CRITERIA!!!'

    # End of the Outer Loops
    print 'SEARCH WAS STOPPED AT TRIAL NUMBER: %d' %icall
    print 'NORMALIZED GEOMETRIC RANGE = %f'  %gnrng
    print 'THE BEST POINT HAS IMPROVED IN LAST %d LOOPS BY %f' %(kstop,criter_change)

    #reshape BESTX
    BESTX=BESTX.reshape(BESTX.size/nopt,nopt)

    # END of Subroutine sceua
    return bestx