%module crest_core
%{
extern double* model(float Rain, float PET, float RI, float RS,
                float SS0, float SI0, float W0, float RainFact, float Ksat,
                float WM, float B, float IM, float KE, float coeM,
                float expM, float coeR, float coeS, float KS, float KI, int timestep);

extern int checkWaterBalance(float P, float ET, float RI, float RS, float SS0, float SI0, float W0);
%}
// %include "carrays.i"
// %array_class(float, model);

// %typemap(out) float*model{
//     int i;
//     //$1, $1_dim0, $1_dim1
//     $result= PyList_New(5);
//     for (i=0;i<5;i++){
//         PyObject *o = PyFloat_FromDouble((double) $1[i]);
//         PyList_SetItem($result,i,o);
//     }
// }

// include "crest_core.c"
double* model(float Rain, float PET, float RI, float RS,
                float SS0, float SI0, float W0, float RainFact, float Ksat,
                float WM, float B, float IM, float KE, float coeM,
                float expM, float coeR, float coeS, float KS, float KI, int timestep);

extern int checkWaterBalance(float P, float ET, float RI, float RS, float SS0, float SI0, float W0);