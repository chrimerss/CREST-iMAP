# Changelog

## 2.0.0 — 2026-08-17

First release of the rewritten CREST-iMAP. The model is still the coupled
hydrologic–hydraulic model of the v1 papers, but both halves are new code: ~2,000
lines of PyTorch in place of ~200,000 lines of Python 2 and vendored C, running on
CPU or GPU and differentiable end to end.

**v1.x is not gone.** It is archived unchanged at the [`v1-legacy`](
https://github.com/chrimerss/CREST-iMAP/tree/v1-legacy) branch and the
[`v1-final`](https://github.com/chrimerss/CREST-iMAP/releases/tag/v1-final) tag.
It is no longer on `master`.

### Added

- **Well-balanced shallow-water solver** (`crestimap/solver.py`). Audusse et al.
  (2004) hydrostatic reconstruction with HLL flux, MUSCL/minmod second order and
  SSP-RK2 stepping; point-implicit Manning friction; Kurganov–Petrova desingularised
  wet/dry velocities. Full momentum is retained, so trans/supercritical flow and
  shocks are captured. Exact lake-at-rest C-property, wet and dry, at both orders.
- **Differentiability.** The whole simulation is torch ops, so autograd runs through
  it: Manning n fields, bed elevation, initial conditions, CREST parameters and
  forcing are all gradient-calibratable, with `checkpoint_every` to trade compute for
  memory on long events. This replaces v1's SCE-UA / GA / MCMC / particle-swarm search.
- **CREST water balance** (`crestimap/lsm.py`, `CrestLSM`). VIC-curve partition of
  rainfall into infiltration-excess runoff and soil storage, with interflow, run-on
  re-infiltration (Li et al. 2022) and an optional baseflow reservoir. Verified
  bit-identical to v1's Cython `crest_simp.pyx`. Runs the whole grid as tensor ops
  rather than v1's per-centroid `numpy.apply_along_axis`.
- **EF5/CREST upstream coupling** (`crestimap/forcing.py`): runoff-grid forcing,
  initial state from routed discharge, channel-stage coupling — the CREST-AI path,
  for when the hydrology runs ahead of the model instead of inside it.
- **Event runner** (`crestimap/event.py`): one flood event end to end — DEM fetch,
  forcing, solve, compact uint16-cm depth frames, manifest.
- **Multi-event GPU worker** (`crestimap/worker.py`, `crestimap/session.py`):
  resident per-event sessions with a cooperative scheduler and incremental publishes.
- **On-demand 3DEP DEM tiles** (`crestimap/dem.py`), 1″ (~30 m) and 1/3″ (~10 m),
  locally cached.
- **Hurricane Harvey benchmark** (`benchmarks/harvey/`, `docs/BENCHMARK_HARVEY.md`):
  driver, peak-depth reducer and scorer against the 813 USGS STN event-180
  high-water marks, plus a matched-control comparison against a local-inertial core.
- **Validation suite** (21 tests): C-property wet and dry at both orders, Stoker
  dam-break against the analytic solution, closed-basin mass balance, autograd
  vs finite differences, EF5-grids-to-solver volume balance, and the CREST layer
  against v1's compiled routine.
- Model structure and framework diagrams, and the Harvey inundation animation,
  migrated from v1 and re-encoded for the web.

### Changed

- **Grid**: regular DEM-aligned raster with cell-centred states, replacing v1's
  unstructured triangular ANUGA mesh.
- **CREST coupling**: a module the caller drives, not a branch inside the solver's
  `evolve` loop. Either half can be run on its own.
- **Python 3.10+ / PyTorch**, replacing Python 2.7 with vendored ANUGA and 28
  compiled extensions.

### Removed

- The vendored ANUGA fork and the bundled `python2` virtualenv (26,972 files).
  Both live on at `v1-legacy` / `v1-final`.

### Known limitations

- **Runtime.** On the Harvey benchmark the solver is ~38× slower in wall clock than
  a `torch.compile`-fused local-inertial core (8.59 h vs 13.4 min for a 10-day event
  on 11.2 M cells, A100). This is per-step implementation cost, not the numerics —
  v2 took *fewer, larger* timesteps, so its CFL was never the constraint. Fusing
  `_flux_div` is the open item.
- **No tiling or active-cell packing.** The grid is held dense, so ~100 M cells
  (Harris County at 10 m) is out of reach as written.
- **`run_event` takes a scalar Manning value**, though `SWESolver` accepts a full
  roughness field.
- **Accuracy is on par with, not ahead of, the local-inertial baseline** on the
  Harvey high-water marks (0.84 m vs 0.81 m MAE). v2's measurable gains are in flood
  extent (81 % vs 74 % of marks wet) and deep-flood fill (−0.18 m vs −0.35 m bias).
- **No license file.** The repository declares no license, so the default is "all
  rights reserved" — worth resolving for a citable research tool.

### Citation

No paper for v2 yet; cite the CREST-iMAP papers:

> Li, Z., Chen, M., Gao, S., Luo, X., Gourley, J., Kirstetter, P., Yang, T., Kolar,
> R., McGovern, A., Wen, Y., Rao, B., Yami, T., Hong, Y., 2021. CREST-iMAP v1.0: A
> fully coupled hydrologic-hydraulic modeling framework dedicated to flood inundation
> mapping and prediction. *Environmental Modelling & Software*, 141, 105051.
> https://doi.org/10.1016/j.envsoft.2021.105051

> Li, Z., Chen, M., Gao, S., Wen, Y., Gourley, J. J., Yang, T., Kolar, R., & Hong,
> Y., 2022. Can re-infiltration process be ignored for flood inundation mapping and
> prediction during extreme storms? A case study in Texas Gulf Coast region.
> *Environmental Modelling & Software*, 155, 105450.
> https://doi.org/10.1016/j.envsoft.2022.105450

---

## v1.1 and earlier

See the [`v1-legacy`](https://github.com/chrimerss/CREST-iMAP/tree/v1-legacy) branch.
v1 tracked changes in the README's "Updates" section rather than a changelog.
