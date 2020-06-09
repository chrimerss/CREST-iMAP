# Optional - turn off bytecode (.pyc files)
import sys
sys.dont_write_bytecode = True

import numpy as np
import emcee
from ..test_functions import functn

# def lnprob(x, ivar):
    # return -0.5*np.sum(ivar * x**2)

def optimization(bl, bu, pf):
	ndim = pf['num_vars']
	nwalkers = 100
	ivar = 1./np.random.rand(ndim)
	p0 = [np.random.rand(ndim) for i in xrange(nwalkers)]

	lnprob = functn.evaluate()

	sampler = emcee.EnsembleSampler(nwalkers, ndim, lnprob, args=[ivar])
	sampler.run_mcmc(p0, 1000)

