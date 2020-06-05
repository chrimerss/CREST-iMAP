swig -python crest_core.i
gcc -fPIC -c crest_core.c crest_core_wrap.c -I/home/ZhiLi/CRESTHH/python2/include/python2.7
gcc -shared crest_core.o crest_core_wrap.o -o _crest_core.so
