from sys import exit
import argparse
import sobol_analyze, morris, extended_fast, dgsm, delta, sobol_svm, moments, correlations, confidence, hypothesis

parser = argparse.ArgumentParser(description='Perform sensitivity/uncertainty analysis on model output')

parser.add_argument('-m', '--method', type=str, choices=['sobol', 'morris', 'fast', 'moments', 'confidence', 'correlations', 'hypothesis',\
'dgsm', 'delta', 'sobol_svm'], required=True)
parser.add_argument('-p', '--paramfile', type=str, required=True, help='Parameter range file')
parser.add_argument('-I', '--model-input-file', type=str, required=False, help='Model input file')
parser.add_argument('-Y', '--model-output-file', type=str, required=True, help='Model output file')
parser.add_argument('-c', '--column', type=int, required=False, default=0, help='Column of output to analyze')
parser.add_argument('--delimiter', type=str, required=False, default=' ', help='Column delimiter in model output file')
parser.add_argument('--sobol-max-order', type=int, required=False, default=2, choices=[1, 2], help='Maximum order of sensitivity indices to calculate (Sobol only)')
parser.add_argument('-r', '--sobol-bootstrap-resamples', type=int, required=False, default=1000, help='Number of bootstrap resamples for Sobol confidence intervals')
parser.add_argument('-N', '--N-rbf', type=int, required=False, default=10000, help='Number of sample points on the RBF surface')
parser.add_argument('-k', '--n-folds', type=int, required=False, default=10, help='Number of folds in SVR cross-validation')
parser.add_argument('-t', '--training-sample', type=int, required=False, default=None, help='Subsample size to train SVR. Default uses all points in dataset.')
args = parser.parse_args()

if args.method == 'sobol':
    calc_second_order = (args.sobol_max_order == 2)
    sobol_analyze.analyze(args.paramfile, args.model_output_file, args.column, calc_second_order, num_resamples = args.sobol_bootstrap_resamples, delim = args.delimiter)
elif args.method == 'morris':
    if args.model_input_file is not None:
        morris.analyze(args.paramfile, args.model_input_file, args.model_output_file, args.column, delim = args.delimiter)
    else:
        print "Error: model input file is required for Method of Morris. Run with -h flag to see usage."
        exit()
elif args.method == 'fast':
    extended_fast.analyze(args.paramfile, args.model_output_file, args.column, delim = args.delimiter)
elif args.method == 'moments':
    moments.analyze(args.model_output_file, args.column, delim = args.delimiter)
elif args.method == 'correlations':
    correlations.analyze(args.paramfile, args.model_input_file, args.model_output_file, args.column, delim = args.delimiter)
elif args.method == 'confidence':
    confidence.analyze(args.model_output_file, args.column, delim = args.delimiter)
elif args.method == 'hypothesis':
    hypothesis.analyze(args.paramfile, args.model_input_file, args.model_output_file, args.column, delim = args.delimiter)
elif args.method == 'dgsm':
    dgsm.analyze(args.paramfile, args.model_input_file, args.model_output_file, args.column, delim=args.delimiter, num_resamples=args.sobol_bootstrap_resamples)
elif args.method == 'delta':
    delta.analyze(args.paramfile, args.model_input_file, args.model_output_file, args.column, delim=args.delimiter, num_resamples=args.sobol_bootstrap_resamples)
elif args.method == 'sobol_svm':
    sobol_svm.analyze(args.paramfile, args.model_input_file, args.model_output_file, args.N_rbf, args.column, delim=args.delimiter, n_folds=args.n_folds, training_sample=args.training_sample)