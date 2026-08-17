# CREST-iMAP v2 — design

Successor to the ANUGA-based CREST-iMAP v1.x (Li et al. 2021, EMS; Chen et
al. 2021, JHM). Goals, in order:

1. **Stability/accuracy**: replace the solver with a well-balanced,
   positivity-preserving finite-volume scheme — Audusse et al. (2004)
   hydrostatic reconstruction + HLL, MUSCL/minmod second order. Full
   momentum is retained, so trans/supercritical flow and shocks are
   captured (the known weak spot of local-inertial solvers such as
   LISFLOOD-FP and Inunda).
2. **Differentiability**: the solver is pure PyTorch; autograd runs through
   the entire simulation (verified against finite differences). Gradient
   targets: Manning n fields, bathymetry corrections, forcing. Long events
   backprop via gradient checkpointing (`checkpoint_every`).
3. **Separation of concerns**: the CREST water balance is a module
   (`crestimap/lsm.py`), not a branch inside the solver loop. v1 called the
   scalar Cython `crest_simp.model` once per centroid from
   `generic_domain.evolve`, through `numpy.apply_along_axis`; v2 runs the
   same water balance over the whole grid as tensor ops — vectorised, GPU
   resident, and differentiable alongside the solver. Either half can be
   driven on its own. In the CREST-AI deployment EF5/CREST instead runs
   upstream and supplies initial conditions (2-D Q, SM) and lateral-inflow
   forcing (surface + subsurface runoff grids) through `forcing.py`.

## Numerical scheme

- Regular DEM-aligned raster grid; states (h, hu, hv) cell-centered.
- Hydrostatic reconstruction at faces: `zf = max(zL, zR)`,
  `h* = max(0, h + z - zf)`; per-side pressure corrections
  `g/2 (h^2 - h*^2)` keep the scheme well-balanced; second order
  reconstructs (h, eta = h + z, u, v) with minmod so the C-property is
  exact at both orders (verified to 1e-12, wet and partially dry).
- HLL flux with Einfeldt-type wave-speed bounds; branchless formulation
  (safe for autograd).
- SSP-RK2; CFL-adaptive dt, detached from the graph.
- Desingularized velocities (Kurganov & Petrova 2007) at wet/dry fronts.
- Point-implicit Manning friction (closed form).
- Lateral inflow source term = rainfall excess / EF5 runoff [m/s].

## Validation (crestimap/tests)

| test | result |
|---|---|
| lake at rest, irregular bed, orders 1+2 | residual < 1e-12 |
| lake at rest with dry hills | residual < 1e-12 |
| Stoker wet-bed dam break (2nd order, 800 cells) | rel. L1 < 3% |
| closed-basin mass balance with inflow | error < 1e-10 |
| autograd vs central FD (Manning n, bed scale) | rel. diff < 1e-4 |

Next validation tier: UK EA benchmark cases, then Hurricane Harvey
(Brays Bayou) against the v1.x results and USGS HWMs.

## CREST-AI integration (event-triggered)

- Trigger: nowcast heatmap "flood" warning level -> basin selection ->
  domain bbox + window (spin-up before t0 through nowcast horizon).
- EF5 event run produces 2-D Q/SM initial-condition grids and
  surface+subsurface runoff forcing grids.
- Compute placement: basin-scale (~1e6 cells at 10 m) runs in minutes on
  a GPU; event-triggered dedicated GPU Space (or chunked ZeroGPU with
  state checkpoints) — not CONUS-continuous.
- Outputs: depth + max-depth rasters at 15-min cadence, served through the
  existing CREST-AI 2-D frame pipeline.

## Repository layout

- `crestimap/` — v2 package (Python 3, PyTorch).
- v1.x legacy (Python 2 + vendored ANUGA, `cresthh/` etc.) was removed
  from this branch 2026-08-12. It is archived unchanged at the `v1-legacy`
  branch and the `v1-final` tag (it is no longer on `master`).
