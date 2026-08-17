# CREST-iMAP v2

**Coupled Routing Excess STorage inundation MApping and Prediction —
version 2.** A differentiable, coupled hydrologic–hydraulic flood model
written in PyTorch, and the hydrodynamic engine of the
[CREST-AI](https://github.com/mchen15ouedu/CREST_AI) real-time flood
dashboard.

v2 is a ground-up rewrite of the dynamic core: the vendored ANUGA solver of
v1.x is replaced by a modern well-balanced finite-volume scheme, in ~2,000
lines of PyTorch rather than ~200,000 lines of Python 2 and C. The CREST
water balance is kept — [`crestimap/lsm.py`](crestimap/lsm.py) is a torch
port of v1's cell water balance, verified bit-identical to v1's Cython
`crest_simp.pyx` — so v2 is still the coupled model the CREST-iMAP papers
describe, now differentiable end to end. Where EF5/CREST already runs
upstream (the CREST-AI deployment), [`crestimap/forcing.py`](crestimap/forcing.py)
ingests its runoff and discharge grids instead.

**CREST-iMAP v1.x** (Python 2.7 + vendored ANUGA, CPU-only) is archived at
the **`v1-legacy`** branch and the **`v1-final`** tag. It is not on `master`
any more. Its bundled `python2` virtualenv and prebuilt extensions still run
as-is; see the `v1-final` tag annotation for how to run or port it.

Validated on Hurricane Harvey against 813 USGS high-water marks —
[`docs/BENCHMARK_HARVEY.md`](docs/BENCHMARK_HARVEY.md).

## Numerical scheme

- Regular DEM-aligned raster grid, cell-centered states (h, hu, hv).
- Hydrostatic reconstruction of Audusse et al. (2004): well-balanced
  (exact lake-at-rest C-property, machine precision) and
  positivity-preserving, at first and second order.
- HLL flux; second order via MUSCL/minmod reconstruction in
  (h, eta, u, v).
- SSP-RK2 time stepping with adaptive CFL timestep.
- Point-implicit Manning friction (closed form, differentiable).
- Desingularized wet/dry velocities (Kurganov & Petrova 2007) — stable
  fronts, no NaN gradients.
- Everything is torch tensor ops: the entire simulation is
  **differentiable end to end** w.r.t. Manning n, bed elevation, initial
  conditions, and forcing (autograd calibration), and runs unchanged on
  CPU or GPU.

Validated in `crestimap/tests`: exact C-property (wet and dry, both
orders), Stoker dam-break analytic solution, mass conservation to 1e-9,
autograd gradients vs finite differences, and an end-to-end
EF5-grids-to-solver volume balance.

## Installation

Python >= 3.10, torch >= 2.0.

```bash
pip install -e ".[geo]"      # rasterio + requests for DEM/forcing I/O
pip install -e ".[geo,test]" # + pytest
```

## Quick start

```python
import torch
from crestimap import SWESolver

ny, nx = 200, 200
z = torch.zeros(ny, nx)                        # bed elevation [m]
h = torch.zeros(ny, nx); h[:, :nx // 2] = 1.0  # dam break
solver = SWESolver(z, dx=10.0, dy=10.0, n_manning=0.03, order=2, bc="wall")
h, qx, qy = solver.run(h, torch.zeros_like(h), torch.zeros_like(h),
                       t_end=300.0)
```

Make `z` or `n_manning` require grad and backpropagate through `run()` to
calibrate them against observed depths.

## Package layout

| Module | Purpose |
|---|---|
| `crestimap/solver.py` | the well-balanced SWE solver (`SWESolver`) |
| `crestimap/lsm.py` | CREST water balance (`CrestLSM`): rainfall → runoff, soil moisture, run-on re-infiltration, baseflow |
| `crestimap/forcing.py` | EF5/CREST coupling: runoff-grid forcing, initial state from routed discharge, channel-stage coupling |
| `crestimap/dem.py` | on-demand USGS 3DEP DEM tiles (1" ~30 m, 1/3" ~10 m), local cache |
| `crestimap/event.py` | `EventConfig` / `run_event`: one flood event end to end (DEM, forcing, solve, depth frames, manifest) |
| `crestimap/io.py` | compact uint16-centimeter GeoTIFF depth frames |
| `crestimap/analytic.py` | analytic references (Stoker dam break) |
| `crestimap/tests/` | validation suite (`pytest crestimap/tests`) |

## Deployment in CREST-AI

The CREST-AI dashboard triggers an event when its AI nowcast flags a
flood at a USGS gauge that observations confirm: EF5 runs the basin in
nowcast mode with gridded runoff output, then `run_event` simulates 2-D
inundation at the DEM's native resolution and publishes depth frames.
Design and operations documents in [`docs/`](docs):

| Document | Contents |
|---|---|
| [`DESIGN_V2.md`](docs/DESIGN_V2.md) | solver design and v1 -> v2 rationale |
| [`DESIGN_V27_PARALLEL.md`](docs/DESIGN_V27_PARALLEL.md) | full-basin GPU/parallel architecture: job queue, single-GPU worker, multi-GPU subbasin decomposition with ghost-cell halo exchange, degradation ladder |
| [`P1_WORKER_BRIEF.md`](docs/P1_WORKER_BRIEF.md) | executable contract for the HPC GPU event worker |

## Citation

CREST-iMAP v2 (this branch) has no dedicated paper yet; please cite the
original CREST-iMAP papers:

> Li, Z., Chen, M., Gao, S., Luo, X., Gourley, J., Kirstetter, P., Yang,
> T., Kolar, R., McGovern, A., Wen, Y., Rao, B., Yami, T., Hong, Y., 2021.
> CREST-iMAP v1.0: A fully coupled hydrologic-hydraulic modeling framework
> dedicated to flood inundation mapping and prediction. Environmental
> Modelling and Software, 141, 105051.
> https://doi.org/10.1016/j.envsoft.2021.105051

> Li, Z., Chen, M., Gao, S., Wen, Y., Gourley, J. J., Yang, T., Kolar, R.,
> & Hong, Y., 2022. Can re-infiltration process be ignored for flood
> inundation mapping and prediction during extreme storms? A case study in
> Texas Gulf Coast region. Environmental Modelling & Software, 155,
> 105450. https://doi.org/10.1016/j.envsoft.2022.105450
