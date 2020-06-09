import numpy as np
from . import ff2n

def sample(n, center=(4, 4), alpha='orthogonal', face='circumscribed'):
    """
    Central composite design
    
    Parameters
    ----------
    n : int
        The number of factors in the design.
    
    Optional
    --------
    center : int array
        A 1-by-2 array of integers, the number of center points in each block
        of the design. (Default: (4, 4)).
    alpha : str
        A string describing the effect of alpha has on the variance. ``alpha``
        can take on the following values:
        
        1. 'orthogonal' or 'o' (Default)
        
        2. 'rotatable' or 'r'
        
    face : str
        The relation between the start points and the corner (factorial) points.
        There are three options for this input:
        
        1. 'circumscribed' or 'ccc': This is the original form of the central
           composite design. The star points are at some distance ``alpha``
           from the center, based on the properties desired for the design.
           The start points establish new extremes for the low and high
           settings for all factors. These designs have circular, spherical,
           or hyperspherical symmetry and require 5 levels for each factor.
           Augmenting an existing factorial or resolution V fractional 
           factorial design with star points can produce this design.
        
        2. 'inscribed' or 'cci': For those situations in which the limits
           specified for factor settings are truly limits, the CCI design
           uses the factors settings as the star points and creates a factorial
           or fractional factorial design within those limits (in other words,
           a CCI design is a scaled down CCC design with each factor level of
           the CCC design divided by ``alpha`` to generate the CCI design).
           This design also requires 5 levels of each factor.
        
        3. 'faced' or 'ccf': In this design, the star points are at the center
           of each face of the factorial space, so ``alpha`` = 1. This 
           variety requires 3 levels of each factor. Augmenting an existing 
           factorial or resolution V design with appropriate star points can 
           also produce this design.
    
    Notes
    -----
    - Fractional factorial designs are not (yet) available here.
    - 'ccc' and 'cci' can be rotatable design, but 'ccf' cannot.
    - If ``face`` is specified, while ``alpha`` is not, then the default value
      of ``alpha`` is 'orthogonal'.
        
    Returns
    -------
    mat : 2d-array
        The design matrix with coded levels -1 and 1
    
    Example
    -------
    ::
    
        >>> central_composite.sample(3)
        array([[-1.        , -1.        , -1.        ],
               [ 1.        , -1.        , -1.        ],
               [-1.        ,  1.        , -1.        ],
               [ 1.        ,  1.        , -1.        ],
               [-1.        , -1.        ,  1.        ],
               [ 1.        , -1.        ,  1.        ],
               [-1.        ,  1.        ,  1.        ],
               [ 1.        ,  1.        ,  1.        ],
               [ 0.        ,  0.        ,  0.        ],
               [ 0.        ,  0.        ,  0.        ],
               [ 0.        ,  0.        ,  0.        ],
               [ 0.        ,  0.        ,  0.        ],
               [-1.82574186,  0.        ,  0.        ],
               [ 1.82574186,  0.        ,  0.        ],
               [ 0.        , -1.82574186,  0.        ],
               [ 0.        ,  1.82574186,  0.        ],
               [ 0.        ,  0.        , -1.82574186],
               [ 0.        ,  0.        ,  1.82574186],
               [ 0.        ,  0.        ,  0.        ],
               [ 0.        ,  0.        ,  0.        ],
               [ 0.        ,  0.        ,  0.        ],
               [ 0.        ,  0.        ,  0.        ]])
        
       
    """
    # Check inputs
    assert isinstance(n, int) and n>1, '"n" must be an integer greater than 1.'
    assert alpha.lower() in ('orthogonal', 'o', 'rotatable', 
        'r'), 'Invalid value for "alpha": {:}'.format(alpha)
    assert face.lower() in ('circumscribed', 'ccc', 'inscribed', 'cci',
        'faced', 'ccf'), 'Invalid value for "face": {:}'.format(face)
    
    try:
        nc = len(center)
    except:
        raise TypeError('Invalid value for "center": {:}. Expected a 1-by-2 array.'.format(center))
    else:
        if nc!=2:
            raise ValueError('Invalid number of values for "center" (expected 2, but got {:})'.format(nc))

    # Orthogonal Design
    if alpha.lower() in ('orthogonal', 'o'):
        H2, a = star(n, alpha='orthogonal', center=center)
    
    # Rotatable Design
    if alpha.lower() in ('rotatable', 'r'):
        H2, a = star(n, alpha='rotatable')
    
    # Inscribed CCD
    if face.lower() in ('inscribed', 'cci'):
        H1 = ff2n.sample(n)
        H1 = H1/a  # Scale down the factorial points
        H2, a = star(n)
    
    # Faced CCD
    if face.lower() in ('faced', 'ccf'):
        H2, a = star(n)  # Value of alpha is always 1 in Faced CCD
        H1 = ff2n.sample(n)
    
    # Circumscribed CCD
    if face.lower() in ('circumscribed', 'ccc'):
        H1 = ff2n.sample(n)
    
    C1 = repeat_center(n, center[0])
    C2 = repeat_center(n, center[1])

    H1 = union(H1, C1)
    H2 = union(H2, C2)
    H = union(H1, H2)

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
	
	
def star(n, alpha='faced', center=(1, 1)):
    """
    Create the star points of various design matrices
    
    Parameters
    ----------
    n : int
        The number of variables in the design
    
    Optional
    --------
    alpha : str
        Available values are 'faced' (default), 'orthogonal', or 'rotatable'
    center : array
        A 1-by-2 array of integers indicating the number of center points
        assigned in each block of the response surface design. Default is 
        (1, 1).
    
    Returns
    -------
    H : 2d-array
        The star-point portion of the design matrix (i.e. at +/- alpha)
    a : scalar
        The alpha value to scale the star points with.
    
    Example
    -------
    ::
    
        >>> star(3)
        array([[-1.,  0.,  0.],
               [ 1.,  0.,  0.],
               [ 0., -1.,  0.],
               [ 0.,  1.,  0.],
               [ 0.,  0., -1.],
               [ 0.,  0.,  1.]])
               
    """
    # Star points at the center of each face of the factorial
    if alpha=='faced':
        a = 1
    elif alpha=='orthogonal':
        nc = 2**n  # factorial points
        nco = center[0]  # center points to factorial
        na = 2*n  # axial points
        nao = center[1]  # center points to axial design
        # value of alpha in orthogonal design
        a = (n*(1 + nao/float(na))/(1 + nco/float(nc)))**0.5
    elif alpha=='rotatable':
        nc = 2**n  # number of factorial points
        a = nc**(0.25)  # value of alpha in rotatable design
    else:
        raise ValueError('Invalid value for "alpha": {:}'.format(alpha))
    
    # Create the actual matrix now.
    H = np.zeros((2*n, n))
    for i in range(n):
        H[2*i:2*i+2, i] = [-1, 1]
    
    H *= a
    
    return H, a
	
	
def union(H1, H2):
    """
    Join two matrices by stacking them on top of each other.
    
    Parameters
    ----------
    H1 : 2d-array
        The matrix that goes on top of the new matrix
    H2 : 2d-array
        The matrix that goes on bottom of the new matrix
    
    Returns
    -------
    mat : 2d-array
        The new matrix that contains the rows of ``H1`` on top of the rows of
        ``H2``.
    
    Example
    -------
    ::
    
        >>> union(np.eye(2), -np.eye(2))
        array([[ 1.,  0.],
               [ 0.,  1.],
               [-1.,  0.],
               [ 0., -1.]])
               
    """
    H = np.r_[H1, H2]
    return H