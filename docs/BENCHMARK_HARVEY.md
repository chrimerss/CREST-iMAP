# Hurricane Harvey benchmark — v2 dynamic core vs the local-inertial baseline

Ran v2 against real observations before merging. Summary up front: **the solver is
correct and the numerics are sound; on this event it matches the local-inertial
baseline on accuracy and costs ~38× more compute, and that cost is an unfused-kernel
problem rather than anything about the scheme.**

### How it was configured

v2 ships as hydrodynamics-only, with the CREST water balance deliberately dropped. That
isn't the configuration we can adopt — CREST-iMAP is a *coupled* model and the v1 papers
are about that coupling. So it was benchmarked as **"keep CREST, replace only the dynamic
core"**, which is what this PR now implements via the new `crestimap/lsm.py`.

The CREST layer is verified bit-identical to v1's own Cython `crest_simp.pyx`
(max |diff| **1e-16 m** over 4000 random parameter/forcing combinations, pinned by
`crestimap/tests/test_lsm.py`), so the experiment isolates the hydrodynamics.

**Event:** Harvey, 2017-08-22 → 09-01, Harris County @ 30 m (3373×3323 = 11.2 M cells,
6.32 M valid), MRMS MultiSensor_QPE_01H hourly forcing (storm total 771 mm mean /
1197 mm max — matches observed), NLCD-2019 Manning field, EF5 CREST parameters, run-on
re-infiltration, wall outer BC. **Scored against the 813 USGS STN event-180 high-water
marks.** Both arms share an identical grid, DEM, Manning, forcing, CREST layer, window
and BC — only the dynamic core differs.

### Accuracy — indistinguishable from the baseline

Peak-depth MAE at the HWMs (metres):

| HWM subset | local-inertial baseline | **v2 (Audusse/HLL)** |
|---|---|---|
| all, common coverage (n=487) | **0.81** (bias +0.41, wet 74 %) | 0.84 (+0.50, 79 %) |
| riverine (n=386) | **0.86** (+0.34, 77 %) | 0.88 (+0.45, 82 %) |
| riverine, quality≥Fair (n=247) | **0.74** (+0.10, 75 %) | 0.76 (+0.23, 81 %) |
| riverine, significant floods hag≥0.5 m (n=167) | 0.74 (−0.35, 74 %) | **0.72** (−0.18, 81 %) |

Differences of 0.02–0.03 m against a ~0.8 m error scale are noise. Scored on the
published-table basis v2 lands at **MAE 0.69 m** — mid-SOTA for this event, ahead of
SFINCS (0.83), CREST-iMAP v1's published 0.91, Fathom/LISFLOOD-FP (1.03) and
Delft3D-FM+SWAN (1.34).

**Where v2 genuinely wins** is the known weakness of local-inertial routing: on
significant floods it under-fills by only −0.18 m vs −0.35 m, and wets 81 % of HWM
points vs 74 %. Better extent capture and deep-flood fill — the full-momentum treatment
earning its keep — but not better depth error.

### Cost — ~38×, and it's recoverable

| | steps | mean dt | wall clock | per step | peak GPU |
|---|---|---|---|---|---|
| local-inertial (`torch.compile`-fused) | 700,728 | 1.233 s | **802.9 s** (13.4 min) | 1.15 ms | — |
| **v2** (well-balanced HLL, unfused) | 580,927 | 1.487 s | **30,920 s** (8.59 h) | 53.2 ms | 3.27 GiB |

The important detail: **v2 took fewer, larger timesteps** (mean dt 1.487 s vs 1.233 s),
so the full-momentum CFL was never the constraint. The entire gap is per-step
implementation cost. The baseline's hot step is fused into a few HBM passes and is
bandwidth-bound at ~87 % of A100 peak; v2's `_flux_div` streams ~2000 unfused array
passes per step. Fusing it should recover most of the 38×.

### Verification of the PR as it stands

- Full test suite passes (14/14), plus 7 new LSM tests.
- Lake-at-rest C-property holds on the real Harris DEM: max |dh| = **1.9e-6 m** in
  float32 (float32 round-off at z ≈ 100 m, consistent with the 1e-12 float64 unit test).
- Mass balance over the 10-day run is consistent: 427 mm domain-mean rain → 260 mm CREST
  overland → 27.6 mm re-infiltrated.

### Recommended follow-ups (not blockers)

1. **Fuse the solver step** (`torch.compile` over `_flux_div`) — the single highest-value
   change; most of the 38× lives here.
2. **Tiling / active-cell packing.** v2 holds the whole grid dense, so 10 m Harris
   (~100 M cells) is out of reach as written.
3. **Spatially varying Manning in `run_event`** — the solver accepts an `n` field, but
   `EventConfig.n_manning` is a scalar, so event runs can't use a roughness raster.
4. **Gage-hydrograph benchmark.** Only peak depth was scored here; the temporal skill
   comparison is still unrun for v2.

### Caveats on these numbers

Both arms use the 30 m block-mean DEM with no subgrid channel, so both over-pond
relative to a 10 m run (peak ~21 m — enclosed-basin mass conservation with 771 mm of
rain and no outlet, not instability). In the deep Houston core both 30 m arms degrade
(1.05 / 1.08) against v1's channel-resolved published grid (0.69) — a
resolution/conveyance effect, not a core effect.

Full write-up, reproduction commands and the matched-control config are in
`docs/HARVEY_SOTA_BENCHMARK.md` §3.1.
