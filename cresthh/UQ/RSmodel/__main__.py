from sys import exit
import argparse
import gp, SVR, DT, kNN, BayesianRidge, ElasticNet,\
OrdinaryLeastSquares, LAR, Lasso, Ridge, SGD, Lars

parser = argparse.ArgumentParser(description='Perform regression analysis on model output')

parser.add_argument('-m', '--method', type=str, choices=['gp', 'svm', 'tree', 'forest', 'MARS',\
'kNN', 'OLS', 'Ridge', 'Lasso', 'LAR', 'Lars', 'Bayesian', 'SGD', 'ElasticNet'], required=True)
parser.add_argument('-I', '--model-input-file', type=str, required=True, help='Model input file')
parser.add_argument('-Y', '--model-output-file', type=str, required=True, help='Model output file')
parser.add_argument('-c', '--column', type=int, required=False, default=0, help='Column of output to analyze')
parser.add_argument('--delimiter', type=str, required=False, default=' ', help='Column delimiter in model output file')
parser.add_argument('-v', '--cross-validation', type=str, required=False, default='True', help='Perform cross validation analysis on surrogate model')
args = parser.parse_args()

if args.method == 'gp':
    gp.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'svm':
    SVR.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'tree':
    DT.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'forest':
    DT.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'MARS':
    DT.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'kNN':
    args.weights = 'uniform'
    kNN.regression(args.model_input_file, args.model_output_file, args.weights, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'OLS':
    OrdinaryLeastSquares.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'Ridge':
    Ridge.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'Lasso':
    Lasso.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'ElasticNet':
	ElasticNet.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'LAR':
    LAR.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'Lars':
    Lars.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'Bayesian':
    BayesianRidge.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)
elif args.method == 'SGD':   
    SGD.regression(args.model_input_file, args.model_output_file, args.column, delim = args.delimiter, cv = args.cross_validation)