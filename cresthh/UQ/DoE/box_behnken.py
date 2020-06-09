import numpy as np
from . import ff2n

def sample(n, center=None):
    """
    Create a Box-Behnken design
    
    Parameters
    ----------
    n : int
        The number of factors in the design
    
    Optional
    --------
    center : int
        The number of center points to include (default = 1).
    
    Returns
    -------
    mat : 2d-array
        The design matrix
    
    Example
    -------
    ::
    
        >>> box_behnken.sample(3)
        array([[-1., -1.,  0.],
               [ 1., -1.,  0.],
               [-1.,  1.,  0.],
               [ 1.,  1.,  0.],
               [-1.,  0., -1.],
               [ 1.,  0., -1.],
               [-1.,  0.,  1.],
               [ 1.,  0.,  1.],
               [ 0., -1., -1.],
               [ 0.,  1., -1.],
               [ 0., -1.,  1.],
               [ 0.,  1.,  1.],
               [ 0.,  0.,  0.],
               [ 0.,  0.,  0.],
               [ 0.,  0.,  0.]])
        
    """
    assert n>=3, 'Number of variables must be at least 3'
    
    # First, compute a factorial DOE with 2 parameters
    H_fact = ff2n.sample(2)
    # Now we populate the real DOE with this DOE
    
    # We made a factorial design on each pair of dimensions
    # - So, we created a factorial design with two factors
    # - Make two loops
    Index = 0
    nb_lines = (n*(n-1)/2)*H_fact.shape[0]
    H = repeat_center(n, nb_lines)
    
    for i in range(n - 1):
        for j in range(i + 1, n):
            Index = Index + 1
            H[max([0, (Index - 1)*H_fact.shape[0]]):Index*H_fact.shape[0], i] = H_fact[:, 0]
            H[max([0, (Index - 1)*H_fact.shape[0]]):Index*H_fact.shape[0], j] = H_fact[:, 1]

    if center is None:
        if n<=16:
            points= [0, 0, 0, 3, 3, 6, 6, 6, 8, 9, 10, 12, 12, 13, 14, 15, 16]
            center = points[n]
        else:
            center = n
        
    H = np.c_[H.T, repeat_center(n, center).T].T
    
    return H
	
	
def repeat_center(n, repeat):
    """
    Create the center-point portion of a design matrix
    
    Parameters
    ----------
    n : int
        The number of factors in the original design
    repeat : int
        The number of center points to repeat
    
    Returns
    -------
    mat : 2d-array
        The center-point portion of a design matrix (elements all zero).
    
    Example
    -------
    ::
    
        >>> repeat_center(3, 2)
        array([[ 0.,  0.,  0.],
               [ 0.,  0.,  0.]])
       
    """
    return np.zeros((repeat, n))
