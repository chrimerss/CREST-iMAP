'''
Simplified version of CREST model
The soil moisture is represented by one layer soils
See EF5
'''

__author__='Allen Zhi Li'
__date__='2020/06/18'

cdef int checkWaterBalance(double P, double ET,
                    double SW, double overland, double interflow):

    cdef double balanced

    balanced = P-ET-SW-interflow-overland;
    if balanced<1e-8:
        #print 'Water balanced !'
        return 1;
    else:
        #print 'Water not balanced! deficit: ',balanced
        return 0;

def model(double precipIn, double overland, double petIn, double SM, double Ksat,
        double WM, double B, double IM, double KE,
        double timestep):
    
    cdef double Wo
    cdef double stepHour= timestep/3600.
    cdef double precip= precipIn * timestep*1000.#Input is m/s, convert to mm
    cdef double pet= petIn * timestep*1000. #mm
    cdef double adjPET= pet * KE
    cdef double temX, interflow, interflowExcess
    cdef double precipSoil, precipImperv, Wmaxm, A, R, infiltration, ExcessET, actET
    cdef int balanced
    SM*=1000 # mm
    #print 'soil moisture', SM
    #print 'rain', precip
    #print 'evaporation:', pet

    #SS0+= RS*timestep
    #SI0+= RI*timestep
    # zero division protection
    if WM<=0: WM=100
    if SM<0: SM=0
    if IM<0: IM=0
    elif IM>1.0: IM=0.999999
    if B<0.0: B=1.0
    if Ksat<0.0: Ksat=1.0

    precip+= overland* 1000. # combine precipitation and surface runoff

    if precip>adjPET:
        #available precipitation in soil
        precipSoil= (precip-adjPET) * (1-IM)

        precipImperv = precip -adjPET - precipSoil

        interflowExcess = SM - WM

        if interflowExcess< 0.0:
            interflowExcess= 0.0
        
        if SM>WM: SM= WM

        if SM<WM:

            Wmaxm=WM*(1+B)
            A = Wmaxm * (1-(1.0-SM/WM)**(1.0/(1.0+B)))

            if precipSoil + A >=Wmaxm:
                R= precipSoil-(WM-SM)
                if R<0: R=0.0
                Wo=WM
            else:
                infiltration=WM*((1-A/Wmaxm)**(1+B)-(1-(A+precipSoil)/Wmaxm)**(1+B))
                if infiltration>precipSoil:
                    infiltration= precipSoil
                R = precipSoil - infiltration
                if R<0: R=0.0
                Wo= SM+infiltration
        else:
            R= precipSoil
            Wo= WM
        
        
        temX= (SM+Wo)/WM/2*Ksat*stepHour

        if R<=temX:
            interflow= R
        else:
            interflow= temX

        overland= R- interflow + precipImperv
        
        actET= adjPET

        interflow+= interflowExcess
    else:
        overland=0.0
        interflowExcess= SM -WM

        if interflowExcess<0.0:
            interflowExcess= 0.0
        interflow= interflowExcess
        if SM>WM:
            SM= WM
        
        ExcessET= (adjPET - precip)*SM/WM

        if ExcessET<SM:
            Wo= SM-ExcessET
        else:
            Wo= 0.0
            ExcessET= SM

        actET = ExcessET + precip

    SM= Wo
    balanced= checkWaterBalance(precip, actET, SM, overland, interflow)
    assert balanced==1, 'overland: %.1f precip: %.1f evapo: %.1f Water balance violated!'%(overland, precip, actET)

    #convert back to m or m/s
    overland= overland/1000.
    interflow= interflow/1000.
    SM= SM/1000.
    actET/=(1000.)

    #print 'overland flow:', overland
    #print 'soil moisture: ',SM

    return SM, overland, interflow,actET
