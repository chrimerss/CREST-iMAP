import os
import math
import string
import numpy as np
from ..util import read_param_file

#######################################################
# USER SPECIFIC SECTION
#======================================================
controlFileName = "D:/UQ-PyL/UQ/test_functions/params/SAC.txt"
appInputFiles = "ps_test01.sac"
appInputTmplts = appInputFiles + ".Tmplt"

#######################################################
# FUNCTION: GENERATE MODEL INPUT FILE
#======================================================
def genAppInputFile(inputData,appTmpltFile,appInputFile,nInputs,inputNames):
    infile = open(appTmpltFile, "r")
    outfile = open(appInputFile, "w")
    while 1:
        lineIn  = infile.readline()
        if lineIn == "":
            break
        lineLen = len(lineIn)
        newLine = lineIn
        if nInputs > 0:
            for fInd in range(nInputs):
                strLen = len(inputNames[fInd])
                sInd = string.find(newLine, inputNames[fInd])
                if sInd >= 0:
                    sdata = '%7.3f' % inputData[fInd]
                    strdata = str(sdata)
                    next = sInd + strLen
                    lineTemp = newLine[0:sInd] + strdata +  " " + newLine[next:lineLen+1]
                    newLine = lineTemp
                    lineLen = len(newLine)
        outfile.write(newLine)
    infile.close()
    outfile.close()
    return

#######################################################
# FUNCTION: RUN MODEL
#====================================================== 
def runApplication():
    sysComm = "mopexcal.exe"
    os.system(sysComm)
    return

#######################################################
# FUNCTION: CALCULATE DESIRE OUTPUT
#======================================================
def getOutput():
    Qe = []
    Qo = []
    functn = 0.0
    ignore  = 92
    I = 0
    outfile = open("ps_test01.sac.day", "r")
    for jj in range(ignore):    
        lineIn  = outfile.readline()
    
    while 1:
        lineIn  = outfile.readline()
        if lineIn == "":
            break
        nCols = string.split(lineIn)
        Qe.append(eval(nCols[4]))
        Qo.append(eval(nCols[5]))
        functn = functn + (Qe[I] - Qo[I]) * (Qe[I] - Qo[I])
        I=I+1
    outfile.close()

    functn = functn/I
    functn = math.sqrt(functn)
    return functn

#######################################################
# MAIN PROGRAM
#======================================================
def evaluate(values):
    pf = read_param_file(controlFileName)
    for n in range(pf['num_vars']):
        pf['names'][n] = 'UQ_' + pf['names'][n]

    Y = np.empty([values.shape[0]])
    os.chdir('D:/UQ-PyL/UQ/test_functions/SAC')
    
    for i, row in enumerate(values):
        inputData = values[i]
        genAppInputFile(inputData,appInputTmplts,appInputFiles,pf['num_vars'],pf['names'])
        runApplication()
        Y[i] = getOutput()
        print "Job ID " + str(i+1)
        
    return Y