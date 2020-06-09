# -*- coding: utf-8 -*-
"""
Created on Mon Nov 17 14:18:23 2014

@author: gongwei
"""
# Good Lattice Point method for Uniform Design
import numpy as np
import fractions as fc
import itertools
from ..util.discrepancy import CD2
import matplotlib.pyplot as plt

def sample(n, s, plot=True):
    ''' main function of GLP design'''
    m = EulerFunction(n)
    if m*1.0/n < (1 - 1.0/n):
        m = EulerFunction(n+1)
        if m < 20 and s < 4:
            X = GLP_GV(n+1,s,m)[0:n,:]
        else:
            X = GLP_PGV(n+1,s)[0:n,:]
    else:
        if m < 20 and s < 4:
            X = GLP_GV(n,s,m)
        else:
            X = GLP_PGV(n,s)
            
    if plot:
        plt.figure()
        ax = plt.subplot()
        plt.scatter(X[:,0], X[:,1])
        ax.set_xlim(0,1)
        ax.set_ylim(0,1)
        plt.title('Good Lattice Point(GLP) Sampling')
        plt.show()
        
    return X

def GLP_PGV(n,s):
    ''' type 2 GLP design, if the combination of C(s,m) is large'''
    h = PowerGenVector(n,s)
    X = np.random.uniform(0,1,size=[n,s])
    D = 1e32
    for i in xrange(min(h.shape[0],20)):
        x = glpmod(n,h[i,:])
        x = (x - 0.5)/n
        d = CD2(x)
        if d < D:
            D = d
            X = x
    return X

def GLP_GV(n,s,m):
    ''' type 1 GLP design, if the combination of C(s,m) is small'''
    h = GenVector(n)
    u = glpmod(n,h)
    clist = itertools.combinations(range(m),s)
    X = np.random.uniform(0,1,size=[n,s])
    D = 1e32
    for c in clist:
        x = u[:,c]
        x = (x - 0.5)/n
        d = CD2(x)
        if d < D:
            D = d
            X = x   
    return X
    
def PrimeFactors(n):
    '''generate all prime factors of n'''
    p = []
    f = 2
    while f < n:
        while not n%f:
            p.append(f)
            n //= f
        f += 1
    if n > 1:
        p.append(n)
    
    return p

def EulerFunction(n):
    p = PrimeFactors(n)
    fai = n*(1-1.0/p[0])
    for i in xrange(1,len(p)):
        if p[i] != p[i-1]:
            fai *= 1-1.0/p[i]
    return int(fai)

def GenVector(n):
    h = []
    for i in xrange(n):
        if fc.gcd(i,n) == 1:
            h.append(i)
    return h

def PowerGenVector(n,s):
    a = []
    for i in xrange(2,n):
        if fc.gcd(i,n) == 1:
            a.append(i)
    aa = []
    for i in xrange(len(a)):
        ha = np.mod([a[i]**t for t in xrange(1,s)],n)
        ha = np.sort(ha)
        rep = False
        if ha[0] == 1:
            rep = True
        for j in xrange(1,len(ha)):
            if ha[j] == ha[j-1]:
                rep = True
        if rep == False:
            aa.append(a[i])

    hh = np.zeros([len(aa),s])
    for i in xrange(len(aa)):
        hh[i,:] = np.mod([aa[i]**t for t in xrange(s)],n)
    return hh

def glpmod(n,h):
    ''' generate GLP using generation vector h'''
    m = len(h)
    u = np.zeros([n,m])
    for i in xrange(n):
        for j in xrange(m):
            u[i,j] = np.mod((i+1)*h[j],n)
            if u[i,j] == 0:
                u[i,j] = n
    return u