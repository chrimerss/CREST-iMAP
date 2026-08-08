"""CREST-iMAP v2 — differentiable well-balanced hydrodynamic module.

Python-3 successor to the ANUGA-based CREST-iMAP v1.x. The CREST water
balance is intentionally NOT included: in the CREST-AI deployment the
CREST/EF5 hydrologic model runs upstream and supplies

  * initial conditions  — 2-D discharge (Q) and soil moisture (SM) grids
  * forcing             — surface + subsurface runoff grids per timestep

to this module, which solves the full 2-D shallow-water equations with a
well-balanced positivity-preserving scheme (Audusse et al. 2004 hydrostatic
reconstruction + HLL), implemented in PyTorch so every simulation is
differentiable (autograd calibration of Manning n, bathymetry, forcing).
"""
from .solver import SWESolver, desing_velocity, minmod
from .analytic import stoker_dambreak

__version__ = "2.0.0.dev0"
__all__ = ["SWESolver", "desing_velocity", "minmod", "stoker_dambreak"]
