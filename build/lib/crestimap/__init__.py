"""CREST-iMAP v2 — differentiable coupled hydrologic–hydraulic flood model.

Python-3 successor to the ANUGA-based CREST-iMAP v1.x, carrying both halves of the
coupled model:

  * :mod:`crestimap.lsm`    — the CREST water balance (VIC-curve rainfall→runoff
    partition with soil-moisture state, run-on re-infiltration and optional
    baseflow); a torch port of v1's `crest_simp.pyx`, verified bit-identical to it.
  * :mod:`crestimap.solver` — the 2-D shallow-water dynamic core: full momentum,
    well-balanced and positivity-preserving (Audusse et al. 2004 hydrostatic
    reconstruction + HLL, MUSCL/minmod, SSP-RK2).

Both are pure PyTorch, so a simulation runs unchanged on CPU or GPU and is
differentiable end to end — Manning n, bathymetry, CREST parameters and forcing are
all autograd-calibratable. That is the substantive gain over v1, whose in-loop CREST
called a scalar Cython routine once per mesh centroid.

The upstream coupling is still supported and remains the CREST-AI deployment path:
where EF5/CREST runs ahead of the model, :mod:`crestimap.forcing` ingests its runoff
and discharge grids directly instead of running the water balance here.
"""
from .solver import SWESolver, desing_velocity, minmod
from .lsm import CrestLSM, crest_core
from .analytic import stoker_dambreak
from .event import EventConfig, run_event

__version__ = "2.0.0"
__all__ = ["SWESolver", "desing_velocity", "minmod", "CrestLSM", "crest_core",
           "stoker_dambreak", "EventConfig", "run_event"]
