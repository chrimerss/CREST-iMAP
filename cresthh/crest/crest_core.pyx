'''
Core of CREST model, three layers of soil moistures
'''
__author__='Allen Zhi Li'
__date__='2020/06/05'

cdef int checkWaterBalance(double P, double ET,
                    double RI, double RS, double SS0,
                    double SI0, double W0):

    cdef double balanced
    balanced = P-ET-SS0-SI0-W0-RI-RS;
    if balanced<1e-10:
        print 'Water balanced !'
        return 1;
    else:
        print 'Water not balanced! deficit: ',balanced
        return 0;

def model(double Rain, double PET, double SS0, double SI0,
        double W0, double RainFact, double Ksat,
        double WM, double B, double IM, double KE,
        double coeM, double expM, double coeR,
        double coeS, double KS, double KI, double timestep):

    cdef double effecRain, Epot, WMM, PSoil, temX, ExcI, ExcS, W, A, R, actualEvap;

    effecRain= Rain*RainFact
    EPot= PET * KE

    #SS0+= RS*timestep
    #SI0+= RI*timestep

    if effecRain>EPot:
        #available precipitation in soil
        PSoil= (effecRain-EPot)*(1.0-IM)*timestep
        if W0<WM:
            WMM= WM*(1.0+B)
            A= WMM*(1.0-(1.0-W0/WM)**(1.0/(1.0+B)))
            if PSoil+A>=WMM:
                R= PSoil- (WM-W0)
                W= WM
            else:
                R= PSoil-(WM-W0)+WM*(1.0-(A+PSoil)/WMM)**(1.0+B)

                if R<0: R=0.0;
                W= W0+PSoil-R

        else: #soil is full
            R= PSoil
            W= W0

        # amount of water goes to infiltration
        temX= ((W0+W)/2.0)*Ksat/WM
        if (R<=temX): ExcI= R;
        else: ExcI= temX;

        ExcS= R-ExcI+(effecRain-EPot)*IM

        if ExcS<0: ExcS=0.0;

    else:
        ExcS= 0.0
        ExcI=0.0
        temX= (EPot-effecRain)*W0/WM
        if temX<W0: W= W0-temX;
        else: W=0.0;

    if effecRain>EPot: actualEvap= EPot;
    else: actualEvap= W0-W;

    SS0+= ExcS
    RS= SS0*KS
    SS0= SS0*(1.0-KS)

    SI0+= ExcI
    RI= SI0*KI
    SI0= SI0*(1.0-KI)

    W0= W

    # cdef int balanced = checkWaterBalance(effecRain, actualEvap,
    #                 RI, RS, SS0,
   #                 SI0, W0)
    

    return RI, RS, SI0, SS0, W0, actualEvap