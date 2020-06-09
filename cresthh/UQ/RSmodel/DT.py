from __future__ import division
import numpy as np
from sklearn import tree
from sklearn import cross_validation
from sklearn import metrics
import matplotlib.pyplot as plt

def regression(input_file, output_file, column = 0, delim = ' ', cv = True, fold = 10, plot = True):

    Y = np.loadtxt(output_file, delimiter = delim)
    X = np.loadtxt(input_file, delimiter = delim)

    if len(Y.shape) == 1: Y = Y.reshape((len(Y),1))
    if len(X.shape) == 1: X = X.reshape((len(X),1))
    
    if Y.ndim > 1:
        Y = Y[:, column]

    model = tree.DecisionTreeRegressor()
		
    if cv:
        scores = cross_validation.cross_val_score(model, X, Y, cv = 10, score_func = metrics.mean_squared_error)
        print "The k-fold mean square error cross validation scores are: \n" + str(scores)
        print "The mean value of the scores is: " + str(scores.mean())
        print "The standard deviation of the scores is: " + str(scores.std())

        if plot:
            fig = plt.figure()
            plt.boxplot(scores,0,'gD')
            plt.xlabel('Desicion Tree Regression')
            plt.ylabel('Mean Square Error')
            plt.title('Cross validation results of DT regression model')
            plt.show()
			
    else:
        model.fit(X, Y)
        return model