import numpy as np
import matplotlib.pyplot as plt
import _design as design

# Generate Sparse Grid samples
def sample(D, L, plot = True):
    """
    Compute a Sparse Grid.

    Parameters
    ----------
    num_dim     :   int
                    Number of dimensions.
    max_level   :   int
                    The maximum level of the sparse grid.
    rule        :   str
                    The quadrature rule. The default is "CC". Choose from:

                        1. "CC", Clenshaw Curtis Closed Fully Nested rule.
                        2. "F1", Fejer 1 Open Fully Nested rule.
                        3. "F2", Fejer 2 Open Fully Nested rule.
                        4. "GP", Gauss Patterson Open Fully Nested rule.
                        5. "GL", Gauss Legendre Open Weakly Nested rule.
                        6. "GH", Gauss Hermite Open Weakly Nested rule.
                        7. "LG", Gauss Laguerre Open Non Nested rule.

    Returns
    -------
    grid_point  :   (num_point, num_dim) ndarray
                    The points of the grid.
    grid_weight :   num_point ndarray
                    The weights of the grid points.
    """
    num_point = design.levels_index_size(D, L, 1)
    grid_weight, grid_point = design.sparse_grid(D, L, 1, num_point)
    grid_point = grid_point.T
    
    result = np.empty([grid_point.shape[0], grid_point.shape[1]])
    
    for i in range(grid_point.shape[0]):
        for j in range(grid_point.shape[1]):
            result[i,j] = grid_point[i][j]
            
    if plot:
        plt.figure()
        ax = plt.subplot()
        plt.scatter(result[:,0], result[:,1])
        ax.set_xlim(-1.1, 1.1)
        ax.set_ylim(-1.1, 1.1)
        plt.title('Clenshaw Curtis Closed Fully Nested rule')
        plt.show()
        
    return grid_point