#-------------------------------------------------------------------------------
# Name:        SCE_Python_shared version
# This is the implementation for the SCE algorithm,
# written by Q.Duan, 9/2004 - converted to python by Van Hoey S.2011
#-------------------------------------------------------------------------------
## Refer to paper:
##  'EFFECTIVE AND EFFICIENT GLOBAL OPTIMIZATION FOR CONCEPTUAL
##  RAINFALL-RUNOFF MODELS' BY DUAN, Q., S. SOROOSHIAN, AND V.K. GUPTA,
##  WATER RESOURCES RESEARCH, VOL 28(4), PP.1015-1031, 1992.

import random
import numpy as np
# from ..test_functions import functn
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt

################################################################################
##  Sampling called from SCE
################################################################################

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

def cceua(s,sf,bl,bu,icall,iseed,func):
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

    if not hasattr(func, "__call__"):
        raise ValueError('expected object func is a callable.')


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

    fnew = func(snew)[0]
    icall += 1

    # Reflection failed; now attempt a contraction point:
    if fnew > fw:
        snew[0] = sw + beta * (ce-sw)
        fnew = func(snew)[0]
        icall += 1

    # Both reflection and contraction have failed, attempt a random point;
        if fnew > fw:
            snew = SampleInputMatrix(1,nopt,bu,bl,iseed,distname='randomUniform')
            fnew = func(snew)[0]
            icall += 1

    # END OF CCE
    return snew[0],fnew,icall


def sceua(bl,bu,pf,ngs,func,plot=True):
# This is the subroutine implementing the SCE algorithm,
# written by Q.Duan, 9/2004 - converted to python by Van Hoey S.2011

    # Initialize SCE parameters:
    nopt=len(bl)
    npg=2*nopt+1
    nps=nopt+1
    nspl=npg
    npt=npg*ngs
    bound=bu-bl
    maxn=500
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
    xf=func(x)
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

    print 'The Initial Loop: 0'
    print ' BESTF:  %f ' %bestf
    print ' BESTX:  '
    print bestx
    print ' WORSTF:  %f ' %worstf
    print ' WORSTX: '
    print worstx
    print '     '

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
##                        lpos = 1 + int(np.floor(npg+0.5-np.sqrt((npg+0.5)**2 - npg*(npg+1)*random.random())))
                        lpos = int(np.floor(npg+0.5-np.sqrt((npg+0.5)**2 - npg*(npg+1)*random.random())))
##                        idx=find(lcs(1:k3-1)==lpos)
                        idx=(lcs[0:k3]==lpos).nonzero()  #check of element al eens gekozen
                        if idx[0].size == 0:
                            break

                    lcs[k3] = lpos
                lcs.sort()

                # Construct the simplex:
                s = np.zeros((nps,nopt))
                s=cx[lcs,:]
                sf = cf[lcs]

                snew,fnew,icall=cceua(s,sf,bl,bu,icall,iseed,func)

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
            #end of Evolve sub-population igs for nspl steps:

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

        print 'Evolution Loop: %d  - Trial - %d' %(nloop,icall)
        print ' BESTF:  %f ' %bestf
        print ' BESTX:  '
        print bestx
        print ' WORSTF:  %f ' %worstf
        print ' WORSTX: '
        print worstx
        print '     '

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

    if plot:
        fig = plt.figure()
        ax1 = plt.subplot(121)
        l1 = ax1.plot(BESTX)
        ax1.legend((l1),(pf['names']), shadow=True)
        plt.title('Trace of the different parameters')
        plt.xlabel('Evolution Loop')
        plt.ylabel('Parameters\' value')

        ax2 = plt.subplot(122)
        ax2.plot(BESTF)
        plt.title('Trace of model value')
        plt.xlabel('Evolution Loop')
        plt.ylabel('Model value')

        plt.show()

    # END of Subroutine sceua
    return bestx,bestf,BESTX,BESTF,ICALL