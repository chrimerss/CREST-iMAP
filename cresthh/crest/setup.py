from setuptools import setup
from Cython.Build import cythonize

setup(
    name='Crest',
    ext_modules=cythonize("crest_simp.pyx"),
    zip_safe=False,
)
