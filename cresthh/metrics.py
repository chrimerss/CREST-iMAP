"""
This module contains functions of modern/common hydrologic metrics

__author__='Allen Zhi Li'
__date__='2020-07-10'
__version__=0.1
"""
__all__ =['nse','rmse','me','rb','peak_flow_error','peak_time_error']
import numpy as np

def nse(obs, sim):
    '''
    Nash-Sucliff coefficient

    Args:
    ----------------------
    :obs - np.array object; observed discharge
    :sim - np.array object; simulated discharge

    Returns:
    ----------------------
    :result - float

    Examples:
    ----------------------
    >>> from cresthh import metrics as met
    >>> obs= np.array([0,1,2,3,4])
    >>> sim= np.array([2,3,4,5,6])
    >>> met.nse(obs, sim)
    '''
    norm= (np.abs(sim - obs)) ** 2
    denorm = (np.abs(obs - np.mean(obs))) ** 2

    return 1- (np.sum(norm) / np.sum(denorm))

def rmse(obs, sim):
    '''
    Root Mean Squre Error

    Args:
    ----------------------
    :obs - np.array object; observed discharge
    :sim - np.array object; simulated discharge

    Returns:
    ----------------------
    :result - float

    Examples:
    ----------------------
    >>> from cresthh import metrics as met
    >>> obs= np.array([0,1,2,3,4])
    >>> sim= np.array([2,3,4,5,6])
    >>> met.rmse(obs, sim)
    '''    
    return np.sqrt(np.mean((sim - obs) ** 2))

def me(obs, sim):
    '''
    Mean Error 

    Args:
    ----------------------
    :obs - np.array object; observed discharge
    :sim - np.array object; simulated discharge

    Returns:
    ----------------------
    :result - float

    Examples:
    ----------------------
    >>> from cresthh import metrics as met
    >>> obs= np.array([0,1,2,3,4])
    >>> sim= np.array([2,3,4,5,6])
    >>> met.me(obs, sim)
    '''    
    return np.mean(sim - obs)

def pearsonr(obs, sim):
    '''
    Pearson-r correlation coefficient

    Args:
    ----------------------
    :obs - np.array object; observed discharge
    :sim - np.array object; simulated discharge

    Returns:
    ----------------------
    :result - float

    Examples:
    ----------------------
    >>> from cresthh import metrics as met
    >>> obs= np.array([0,1,2,3,4])
    >>> sim= np.array([2,3,4,5,6])
    >>> met.pearsonr(obs, sim)
    '''
    sim_mean = np.mean(sim)
    obs_mean = np.mean(obs)

    top = np.sum((obs - obs_mean) * (sim - sim_mean))
    bot1 = np.sqrt(np.sum((obs - obs_mean) ** 2))
    bot2 = np.sqrt(np.sum((sim - sim_mean) ** 2))

    return top/(bot1*bot2)         

def peak_flow_error(obs, sim):
    '''
    The difference of max flow

    Args:
    ----------------------
    :obs - np.array object; observed discharge
    :sim - np.array object; simulated discharge

    Returns:
    ----------------------
    :result - float

    Examples:
    ----------------------
    >>> from cresthh import metrics as met
    >>> obs= np.array([0,1,2,3,4])
    >>> sim= np.array([2,3,4,5,6])
    >>> met.peak_flow_error(obs, sim)
    '''

    return np.nanmax(obs)- np.nanmax(sim)

def peak_time_error(obs, sim):
    '''
    The difference of time peaks

    Args:
    ----------------------
    :obs - np.array object; observed discharge
    :sim - np.array object; simulated discharge

    Returns:
    ----------------------
    :result - float

    Examples:
    ----------------------
    >>> from cresthh import metrics as met
    >>> obs= np.array([0,1,2,3,4])
    >>> sim= np.array([2,3,4,5,6])
    >>> met.peak_time_error(obs, sim)
    '''    
    return np.argmax(obs) - np.argmax(sim)

def rb(obs, sim):
    '''
    The Relative Bias of flow data

    Args:
    ----------------------
    :obs - np.array object; observed discharge
    :sim - np.array object; simulated discharge

    Returns:
    ----------------------
    :result - float

    Examples:
    ----------------------
    >>> from cresthh import metrics as met
    >>> obs= np.array([0,1,2,3,4])
    >>> sim= np.array([2,3,4,5,6])
    >>> met.rb(obs, sim)
    '''
    ind= np.where(obs!=0)[0]

    return ((sim[ind]-obs[ind])/obs[ind]).sum()/len(sim[ind])