#include <stdio.h>      /* printf */
#include <math.h>       /* pow */
#include <iostream>
using namespace std;
int checkWaterBalance(float P,float ET,float RI,
                        float RS, float SS0, float SI0,
                        float W0){

    bool balanced;
    balanced= P-ET+SS0+SI0+W0-RI-RS;
    if (balanced<1e-10)
    {
        return 1;
    }
    else
    {
        return 0;
    }
        
}

float model(float Rain, float PET, float RI, 
            float RS, float SS0, float SI0,
            float W0, float RainFact, float Ksat,
            float WM, float B, float IM, float KE,
            float coeM, float expM, float coeR,float coeS,
            float KS, float KI, int timestep){

    float effecRain, Epot, WMM, PSoil,temX,ExcI,ExcS,W,A,R,acutalEvap;
    effecRain= Rain*RainFact;
    Epot = PET * KE;
    SS0= SS0+RS;
    SI0= SI0+RI;
    // calculating runoff
    if (effecRain>Epot)
    {
        PSoil = (effecRain-Epot) * (1.0-IM);
        if (W0<WM)
        {
            WMM = WM * (1.0*B);
            A= WMM * pow(1.0 - (1.0-W0/WM),(1.0/(1.0+B)));
            if (PSoil +A >= WMM)
            {
                R = PSoil - (WM-W0);
                W= WM;
            }
            else
            {
                R= PSoil-(WM-W0)+pow(WM*(1.0-(A+PSoil)/WMM),(1.0+B));
                if (R<0)
                {
                    R=0.0;
                }
                W= W0+PSoil-R;
                
            }
        }
        else
        {
            R= PSoil;
            W= W0;
        }
        
       temX= ((W0+W)/2.0)*Ksat/WM; 
        if (R<=temX)
        {
            ExcI=R;
        }
        else
        {
            ExcI= temX;
        }
        ExcS= R-ExcI+(effecRain-Epot)*IM;
        if (ExcS<0)
        {
           ExcS=0.0;
        }
        
    }
    else
    {
        ExcS= 0.0;
        ExcI=0.0;
        temX= (Epot-effecRain)*W0/WM;
        if (temX<W0)
        {
            W= W0-temX;
        }
        else
        {
            W=0.0;
        }
    
    }
    
    if (effecRain>Epot)
    {
        acutalEvap= Epot;
    }
    else
    {
        acutalEvap= W0-W;
    }
    
    SS0+= ExcS;
    RS= SS0*KS;
    SS0*=(1.0-KS);

    SI0+= ExcI;
    RI= SI0*KI;
    SI0*= (1.0-KI);

    W0=W;
    // check water balance
    checkWaterBalance(Rain, PET, RI, RS, SS0, SI0, W0);

    return (RI, RS, SS0, SI0, W0);
    
}

