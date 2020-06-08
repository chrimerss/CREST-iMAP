from setuptools import setup
from Cython.Build import cythonize

setup(
    name='Crest Model',
    ext_modules=cythonize("crest_core.pyx"),
    zip_safe=False,
)