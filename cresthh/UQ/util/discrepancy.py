import numpy as np
import math

# compute 4 kinds of L2-discrepancy
# [Hickernell, 1998a,b], [Fang et.al., 2000]
# 1: MD2 
# 2: CD2
# 3: SD2
# 4: WD2
# n: number of points
# s: number of dimensions
# Hickernell, F. J. (1998), A generalized discrepancy and quadrature error 
# bound, Math Comput, 67(221), 299-322.
# Hickernell, F. J. (1998), Lattice rules: how well do they measure up? in 
# Random and Quasi-Random Point Sets, edited by P. Hellekalek and G. Larcher, 
# pp. 106-166, Springer-Verlag.

def evaluate(X):
    r1 = MD2(X)
    r2 = CD2(X)
    r3 = SD2(X)
    r4 = WD2(X)
    print "The result of MD2 is: "+str(r1)
    print "The result of CD2 is: "+str(r2)
    print "The result of SD2 is: "+str(r3)
    print "The result of WD2 is: "+str(r4)

def MD2(X):
    ''' Modified L2-discrepancy'''
    num, dim = X.shape
    D1 = (4.0/3.0)**dim
    D2 = 0.0
    
    for k in range(num):
        DD2 = 1.0
        for j in range(dim):
            DD2 = DD2*(3 - X[k,j]**2)
        D2 = D2 + DD2
        
    D3 = 0.0
    for k in range(num):
        for j in range(num):
            DD3 = 1.0
            for i in range(dim):
                DD3 = DD3 * (2 - max(X[k,i],X[j,i]))
            D3 = D3 + DD3

    D = math.sqrt(D1 + D2*(-2**(1-dim)/float(num)) + D3/(num**2))
    return D

def CD2(X):
    ''' Centered L2-discrepancy'''
    num, dim = X.shape
    D1 = (13.0/12.0)**dim
    
    D2 = 0.0 
    for k in range(num):
        DD2 = 1.0
        for j in range(dim):
            DD2 = DD2 * (1 + 0.5*abs(X[k,j]-0.5) - 0.5*abs(X[k,j]-0.5)**2)
        D2 = D2 + DD2
    
    D3 = 0.0
    for k in range(num):
        for j in range(num):
            DD3 = 1.0
            for i in range(dim):
                DD3 = DD3 * (1 + 0.5*abs(X[k,i]-0.5) + 0.5*abs(X[j,i]-0.5) - 0.5*abs(X[k,i]-X[j,i]))
            D3 = D3 + DD3

    D = math.sqrt(D1 + D2*(-2.0/num) + D3/(num**2))
    return D

def SD2(X):
    ''' Symmetric L2-discrepancy'''  
    num, dim = X.shape
    D1 = (4.0/3.0)**dim
    
    D2 = 0.0
    for k in range(num):
        DD2 = 1.0
        for j in range(dim):
            DD2 = DD2 * (1 + 2*X[k,j] - 2*X[k,j]**2)
        D2 = D2 + DD2
        
    D3 = 0.0
    for k in range(num):
        for j in range(num):
            DD3 = 1.0
            for i in range(dim):
                DD3 = DD3 * (1 - abs(X[k,i]-X[j,i]))
            D3 = D3 + DD3

    D = math.sqrt(D1 + D2*(-2.0/num) + D3*((2**dim)/float(num**2)))
    return D

def WD2(X):
    ''' Wrap-around L2-discrepancy''' 
    num, dim = X.shape
    D1 = -(4.0/3.0)**dim

    D3 = 0.0
    for k in range(num):
        for j in range(num):
            DD3 = 1.0
            for i in range(dim):
                DD3 = DD3 * (3.0/2.0 - abs(X[k,i]-X[j,i]) * (1 - abs(X[k,i]-X[j,i])))
            D3 = D3 + DD3
    D = math.sqrt(D1 + D3/(num**2))
    return D