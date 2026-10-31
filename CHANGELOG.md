# Changelog

## Unreleased

### Added

- **Apple Metal backend.** `device="mps"` now runs `run_event` and `EventSession` on
  a Mac GPU, in float32 as those paths already do: 5.7–14x the best CPU rate from
  512² up, but no faster at 128² and slower at 64². On those same two paths,
  `device="auto"` picks CUDA, then Metal, then CPU; elsewhere, resolve it first with
  `resolve_device`. Metal has no float64, so `test_solver` and `test_forcing` still
  need CPU or CUDA. See [`docs/BENCHMARK_METAL.md`](docs/BENCHMARK_METAL.md).

### Fixed

- **Rain on a dry domain created water.** `compute_dt` saw no wave speed on dry
  cells and took `dt_max`, so rain wet them within the step, the second RK stage
  drove depths negative, and clamping those to zero added water: 5.42x the rain
  supplied on a 16x16 grid with one raining cell, 2x on a 40x40 plane at
  `dt_max=3600`. `compute_dt` now accounts for the depth rain adds, and adaptive
  steps (`step` with no `dt`, and `run`) measure the depth they clip and halve `dt`
  until it is under 1e-13 of the water on the grid. Mass error on those cases is now
  about 1e-15. An explicit `dt` is still taken exactly. Expect more attempts per
  step while rain first wets dry rough ground (see `SWESolver.n_retries`).
- **`cfl` above 0.5 is capped with a warning**, and `cfl <= 0` is refused.
- **`run(checkpoint_every=...)` gave wrong gradients.** Checkpoint replays during
  backward picked up the last step's `dt` and rain instead of their own.
- **DEMs the model cannot use now fail instead of producing numbers.** An
  undeclared fill value such as -9999 acted as a pit, a file with no geotransform
  ran with 111 km cells, metric coordinates with no CRS were read as degrees, a
  rotated transform was ignored, and an all-nodata DEM became `-inf`. `SolverGrid`
  refuses all of these, plus elevations outside (-9990, 9000] m, and
  `regrid_to_solver` refuses a forcing grid with no geotransform. Declared nodata
  cells are still filled.
- **NaN cells in a DEM reached the solver.** `from_dem` missed them when the nodata
  tag was absent or NaN, because NaN never compares equal. They are now filled
  like other nodata cells. Cells a GDAL mask band marks invalid are filled too;
  they used to be read as elevations.
- **`output_every_s <= 0` hung the run.** `EventConfig` now refuses it.

### Changed

- **Depth rasters label their own scale.** `write_depth` still stores uint16
  centimeters but now sets a GDAL scale of 0.01 and units of `m`, so other tools can
  read meters. `read_depth` and the pixel values are unchanged.

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
