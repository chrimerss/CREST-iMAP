[![Python 2.7](https://img.shields.io/badge/python-2.7-blue.svg)](https://www.python.org/downloads/release/python-275/)

# CREST-iMAP

## Coupled Routing Excess STorage inundation MApping and Prediction

<img src="img/myanimation.gif">

# Introduction

**Model Framework:**

<img src="img/CRESTHH.png">

The CRESTH/H model framework integrates hydrologic model (CREST) and hydrodynamic model (anuga) to target heavy rainfall-induced flash flood.

Taking advantage of two models, CRESTHH is capable of simulating hydrologic streamflows, flood extend, flood depth, pushing the territory of traditional 1D streamflow simulation to 2D (extent) and 3D (depth).

## Powerful features

1. __Flash flood inundation__

2. __Hydrologic simulation__

3. __Coastal flooding (Tsunami, wave dynamics)
Impact of hydraulic structures (e.g., dam breaks)__

4. __A set of uncertainty/sensitivity analysis__

5. __Easy to use (can setup in Jupyter notebook)__

6. __Parallel computing__

7. __Efficiency (bottlenecks in C)__

8. __Flexible/Optimal mesh design__

# Installation

## Prerequisites

1. Python 2.7
2. pypar
3. GDAL>=2.2.3
4. mesher
5. Cython>=0.25

This package is not migrated to python 3 yet. We recommend to use virtualenv or conda environment to create a standalone environment to install this package.

```
pip install -r requirements.txt
```
## Manual installation

```bash
virtualenv env -p=python2.7
source env/bin/activate
cd pypar & python setup.py install
cd cresthh/crest & python setup.py install
pip install proj affine matplotlib pandas scipy netCDF4==1.5.3 geopandas

```

# Updates

- [x] 2020.06.17 Add options to create longitudinal profile and animation

<img src="img/channel.gif">

- [x] 2020.06.17 Add options to create soil moisture animation

<img src="img/soilmoisture.gif">

- [x] 2020.06.23 Created interface to read .mesh file from mesher. Therefore, it supports creating mesh by considering the heterogeneity of the topography/river networks and so forth.

- [x] 2020.11.12 Pre-simulation for OKC flooding

<img src="img/OKC_flooding.gif">

# TODO

- [ ] Create Docker file to better minimize the installation process
- [ ] Option to provide land cover data and infer friction
- [ ] Complete examples for each feature