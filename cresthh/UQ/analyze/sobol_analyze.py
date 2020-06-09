from __future__ import division
from ..util import read_param_file
from sys import exit
import numpy as np
from scipy.stats import norm
import math
import matplotlib.pyplot as plt

# Perform Sobol Analysis on file of model results
def analyze(pfile, output_file, column = 0, calc_second_order = True, num_resamples = 100, delim = ' ', conf_level=0.95, plot = True):
    
    param_file = read_param_file(pfile)
    Y = np.loadtxt(output_file, delimiter = delim)

    if len(Y.shape) == 1: Y = Y.reshape((len(Y),1))
    
    if Y.ndim > 1:
        Y = Y[:, column]
    
    D = param_file['num_vars']

    if conf_level < 0 or conf_level > 1:
        raise RuntimeError("Confidence level must be between 0-1.")
        
    if calc_second_order:
        if Y.size % (2*D + 2) == 0:
            N = int(Y.size / (2*D + 2))
        else:
            print """
                Error: Number of samples in model output file must be a multiple of (2D+2), 
                where D is the number of parameters in your parameter file.
                (You have calc_second_order set to true, which is true by default.)
              """
            exit()
    else:
        if Y.size % (D + 2) == 0:
            N = int(Y.size / (D + 2))
        else:
            print """
                Error: Number of samples in model output file must be a multiple of (D+2), 
                where D is the number of parameters in your parameter file.
                (You have calc_second_order set to false.)
              """
            exit()
        
    A = np.empty([N])
    B = np.empty([N])
    C_A = np.empty([N, D])
    C_B = np.empty([N, D])
    Yindex = 0
    
    for i in range(N):
        A[i] = Y[Yindex]
        Yindex += 1
        
        for j in range(D):
            C_A[i][j] = Y[Yindex]
            Yindex += 1
        
        if calc_second_order:
            for j in range(D):
                C_B[i][j] = Y[Yindex]
                Yindex += 1
        
        B[i] = Y[Yindex]
        Yindex += 1
    
    # First order (+conf.) and Total order (+conf.)
    Stotal = np.empty(0)
    Sfirst = np.empty(0)
    SfirstConf = np.empty([D, num_resamples])
    StotalConf = np.empty([D, num_resamples])
    print "Parameter First_Order First_Order_Confidence Total_Order Total_Order_Confidence"
    for j in range(D):
        a0 = np.empty([N])
        a1 = np.empty([N])
        a2 = np.empty([N])
        
        for i in range(N):
            a0[i] = A[i]
            a1[i] = C_A[i][j]
            a2[i] = B[i]
            
        S1 = compute_first_order(a0, a1, a2, N)
        S1c = compute_first_order_confidence(a0, a1, a2, N, num_resamples)
        ST = compute_total_order(a0, a1, a2, N)
        STc = compute_total_order_confidence(a0, a1, a2, N, num_resamples)
        
        print "%s %f %f %f %f" % (param_file['names'][j], S1, norm.ppf(0.5 + conf_level / 2) * S1c.std(ddof=1), ST, norm.ppf(0.5 + conf_level / 2) * STc.std(ddof=1))
        if S1 < 0: S1 = 0
        if ST < 0: ST = 0
        Stotal = np.append(Stotal, ST)
        Sfirst = np.append(Sfirst, S1)
        SfirstConf[j,:] = S1c
        StotalConf[j,:] = STc
    
    # Second order (+conf.)
    if calc_second_order:
        
        print "\nParameter_1 Parameter_2 Second_Order Second_Order_Confidence"
        
        Sinter = np.empty([D,D])
        for j in range(D):
            Sinter[j,j] = 0
            for k in range(j+1, D):
                a0 = np.empty([N])
                a1 = np.empty([N])
                a2 = np.empty([N])
                a3 = np.empty([N])
                a4 = np.empty([N])
                
                for i in range(N):
                    a0[i] = A[i]
                    a1[i] = C_B[i][j]
                    a2[i] = C_A[i][k]
                    a3[i] = C_A[i][j]
                    a4[i] = B[i]
                    
                S2 = compute_second_order(a0, a1, a2, a3, a4, N)
                S2c = compute_second_order_confidence(a0, a1, a2, a3, a4, N, num_resamples)
                if S2 >= 0:
                    Sinter[j,k] = S2
                    Sinter[k,j] = S2
                else:
                    Sinter[j,k] = 0
                    Sinter[k,j] = 0

                print "%s %s %f %f" % (param_file['names'][j], param_file['names'][k], S2, S2c)

    if plot:
        plt.figure()
        colors = ['yellowgreen', 'gold', 'lightskyblue', 'lightcoral', 'red', 'green', 'pink', 'blue']
        ax1=plt.subplot(121)
        ax1.pie(100*Sfirst, labels=param_file['names'], colors = colors, autopct='%1.1f%%', shadow=True)
        plt.title('Sobol\' First order SA results')       
        ax2=plt.subplot(122)
        ax2.pie(100*Stotal, labels=param_file['names'], colors = colors, autopct='%1.1f%%', shadow=True)
        plt.title('Sobol\' Total order SA results')
        
        plt.figure()
        ax1=plt.subplot(121)
        SfirstConf = SfirstConf.T
        ax1.boxplot(SfirstConf)
        ax1.set_xticks(np.arange(param_file['num_vars'])+1)
        ax1.set_xticklabels(param_file['names'])
        plt.title('Sobol\' First order SA confidence interval')
        ax2=plt.subplot(122)
        StotalConf = StotalConf.T
        ax2.boxplot(StotalConf)
        ax2.set_xticks(np.arange(param_file['num_vars'])+1)
        ax2.set_xticklabels(param_file['names'])
        plt.title('Sobol\' Total order SA confidence interval')
        
        plt.figure()
        ax = plt.subplot(111)
        plt.imshow(Sinter, cmap=plt.cm.gray, interpolation='nearest')
        plt.colorbar()
        ax.set_xticks(np.arange(param_file['num_vars'])+0.4)
        ax.set_xticklabels(param_file['names'])
        ax.set_yticks(np.arange(param_file['num_vars'])+0.4)
        ax.set_yticklabels(param_file['names'])     
        plt.title('Sobol\' Interaction effect of SA results')

        plt.show()

                
        
def compute_first_order(a0, a1, a2, N):

    c = np.average(a0)
    tmp1, tmp2, tmp3, EY2 = [0.0]*4

    for i in range(N):
        EY2 += (a0[i] - c) * (a2[i] - c)
        tmp1 += (a2[i] - c) * (a2[i] - c)
        tmp2 += (a2[i] - c)
        tmp3 += (a1[i] - c) * (a2[i] - c)
    
    EY2 /= N
    V = (tmp1 / (N - 1)) - math.pow((tmp2 / N), 2.0)
    U = tmp3 / (N - 1)
    
    return (U - EY2) / V

def compute_first_order_confidence(a0, a1, a2, N, num_resamples):
    
    b0 = np.empty([N])
    b1 = np.empty([N])
    b2 = np.empty([N])
    s  = np.empty([num_resamples])
    
    for i in range(num_resamples):
        for j in range(N):
            
            index = np.random.randint(0, N)
            b0[j] = a0[index]
            b1[j] = a1[index]
            b2[j] = a2[index]
        
        s[i] = compute_first_order(b0, b1, b2, N)
    
#    return 1.96 * s.std(ddof=1)
    return s

def compute_total_order(a0, a1, a2, N):
    
    c = np.average(a0)
    tmp1, tmp2, tmp3 = [0.0]*3
    
    for i in range(N):
        tmp1 += (a0[i] - c) * (a0[i] - c)
        tmp2 += (a0[i] - c) * (a1[i] - c)
        tmp3 += (a0[i] - c)
    
    EY2 = math.pow(tmp3 / N, 2.0)
    V = (tmp1 / (N - 1)) - EY2
    U = tmp2 / (N - 1)
    
    return (1 - (U-EY2) / V)

def compute_total_order_confidence(a0, a1, a2, N, num_resamples):
    
    b0 = np.empty([N])
    b1 = np.empty([N])
    b2 = np.empty([N])
    s  = np.empty([num_resamples])
    
    for i in range(num_resamples):
        for j in range(N):
            
            index = np.random.randint(0, N)
            b0[j] = a0[index]
            b1[j] = a1[index]
            b2[j] = a2[index]
        
        s[i] = compute_total_order(b0, b1, b2, N)
    
#    return 1.96 * s.std(ddof=1)
    return s

def compute_second_order(a0, a1, a2, a3, a4, N):
    
    c = np.average(a0)
    EY, EY2, tmp1, tmp2, tmp3, tmp4, tmp5 = [0.0]*7
    
    for i in range(N):
        EY += (a0[i] - c) * (a4[i] - c)
        EY2 += (a1[i] - c) * (a3[i] - c)
        tmp1 += (a1[i] - c) * (a1[i] - c)
        tmp2 += (a1[i] - c)
        tmp3 += (a1[i] - c) * (a2[i] - c)
        tmp4 += (a2[i] - c) * (a4[i] - c)
        tmp5 += (a3[i] - c) * (a4[i] - c)

    EY /= N
    EY2 /= N
    
    V = (tmp1 / (N - 1)) - math.pow(tmp2 / N, 2.0)
    Vij = (tmp3 / (N - 1)) - EY2
    Vi = (tmp4 / (N - 1)) - EY
    Vj = (tmp5 / (N - 1)) - EY2
    
    return (Vij - Vi - Vj) / V

def compute_second_order_confidence(a0, a1, a2, a3, a4, N, num_resamples):
    
    b0 = np.empty([N])
    b1 = np.empty([N])
    b2 = np.empty([N])
    b3 = np.empty([N])
    b4 = np.empty([N])
    s  = np.empty([num_resamples])
    
    for i in range(num_resamples):
        for j in range(N):
            
            index = np.random.randint(0, N)
            b0[j] = a0[index]
            b1[j] = a1[index]
            b2[j] = a2[index]
            b3[j] = a3[index]
            b4[j] = a4[index]
        
        s[i] = compute_second_order(b0, b1, b2, b3, b4, N)
    
    return 1.96 * s.std(ddof=1)
