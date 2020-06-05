%module crest_core
%{
extern float model(float Rain, float PET, float RI, float RS,
                float SS0, float SI0, float W0, float RainFact, float Ksat,
                float WM, float B, float IM, float KE, float coeM,
                float expM, float coeR, float coeS, float KS, float KI, int timestep);

extern int checkWaterBalance(float P, float ET, float RI, float RS, float SS0, float SI0, float W0);
%}


extern float model(float Rain, float PET, float RI, float RS,
                float SS0, float SI0, float W0, float RainFact, float Ksat,
                float WM, float B, float IM, float KE, float coeM,
                float expM, float coeR, float coeS, float KS, float KI, int timestep);

extern int checkWaterBalance(float P, float ET, float RI, float RS, float SS0, float SI0, float W0);