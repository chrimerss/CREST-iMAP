import numpy as np
from ..util import read_param_file
from ..DoE import saltelli
from . import sobol_analyze
from sklearn import svm
from sklearn.grid_search import GridSearchCV
from sklearn.preprocessing import MinMaxScaler

# Build a metamodel with Support Vector Regression (SVR),
# then run Sobol analysis on the metamodel.
# Returns a dictionary with keys 'S1', 'ST', 'S2', 'R2_cv', and 'R2_fullset'
# Where 'R2_cv' is the mean R^2 value from k-fold cross validation,
# 'R2_fullset' is the R^2 value when the metamodel is applied to all observed data,
# and the other entries are lists of size D (the number of parameters)
# containing the indices in the same order as the parameter file


def analyze(pfile, input_file, output_file, N_rbf=10000, column=0, n_folds=10,
            delim=' ', training_sample=None):

    param_file = read_param_file(pfile)
    y = np.loadtxt(output_file, delimiter=delim, usecols=(column,))
    X = np.loadtxt(input_file, delimiter=delim, ndmin=2)
    if len(X.shape) == 1:
        X = X.reshape((len(X), 1))
    D = param_file['num_vars']
    mms = MinMaxScaler()
    X = mms.fit_transform(X)

    # Cross-validation to choose C and epsilon parameters
    print "Cross-validation to choose C and epsilon parameters for Support Vector Machine(SVM) model"
    C_range = [0.01, 0.1, 1, 10, 100]
    gamma_range = [0.001, 0.1, 1, 10]
    eps_range = [0.01, 0.1, 1]
    param_grid = dict(C=C_range, gamma=gamma_range, epsilon=eps_range)
    reg = GridSearchCV(svm.SVR(), param_grid=param_grid, cv=n_folds)
    
    if training_sample is None:
        print "Fit the surrogate model, will be very slow for large dataset."
        reg.fit(X, y)  # will be very slow for large N
    else:
        if training_sample > y.size:
            raise ValueError(
                "training_sample is greater than size of dataset.")
        ix = np.random.randint(y.size, size=training_sample)
        reg.fit(X[ix, :], y[ix])

    print "Calculate Sobol' sensitivity analysis on the surrogate model"
    X_rbf = saltelli.sample(N_rbf, D, plot=False)
    X_rbf = mms.transform(X_rbf)
    y_rbf = reg.predict(X_rbf)

    np.savetxt("y_rbf.txt", y_rbf, delimiter=' ')

    # not using the bootstrap intervals here. For large enough N, they will go to zero.
    # (this doesn't mean the indices are accurate -- check the metamodel R^2)
    sobol_analyze.analyze(pfile, "y_rbf.txt", num_resamples=100)