# P1.6 validation — resident sessions + cooperative scheduler

Worker: HPC, single RTX 4500 Ada (24 GB), fp32, interpreter
`/media/scratch/MengyuChen/conda_envs/nowcast/bin/python` (3.11).
Code under test: `v2` @ `107c8187` (implementation `5aea4809` + CUDA fixes).
Date: 2026-08-14 (gates 1/2/4), 2026-08-15 (gate 3), report filed 2026-08-17.

## Verdict: GO (user confirmed the flip 2026-08-14)

All four gates pass. Flip procedure:
`EVENT_SESSIONS=1 ./run_worker.sh --publish` at a job boundary, with
`CREST_AI_DIR` pointing at the deployed Space's `hf_data` copy (see
"dependencies" below).

## Checklist 1 — full CUDA suite (incl. test_session.py)

`CRESTIMAP_TEST_DEVICE=cuda`: **14/14 passed** (29 m 39 s wall, GPU shared
with the live P1 worker mid-solve — solo it is minutes).

| gate | criterion | result |
|---|---|---|
| 1 continuation | 3 bundle visits vs continuous, J >= 0.99, < 2 cm | **J 1.0000, 0.00 cm** |
| 2 interleave | A,B alternating == each solo | **bit-exact, both events** |
| 4 restart | init_depth resume vs unbroken, gate-1 tolerance | **J 0.9974, 0.36 cm** |

The first CUDA run failed all three session gates: `test_solver.py` /
`test_forcing.py` call `torch.set_default_device(cuda)` at import, which
leaked into `EventSession.__init__`'s CPU-side setup and split tensors
across devices. Fixed in `107c8187` by pinning the channel pre-wet and
init_depth tensors to the grid's device (production never sets a default
device, but the session code is now robust to hosts that do).

## Checklist 2 — gate 3: GPU-minutes per visit at full-basin scale

Real episode `2026081122_03190000` (Gauley River WV) forcing, full basin
`bbox_basin` at native 30 m = 2160x2160 (**4.67 M cells**), driven through
`EventSession` exactly as a `--sessions --no-publish --once` visit would
(the live queue entry was claimed by the running P1 worker, so the session
was driven directly on the same bundle rather than stealing the claim).

- anchored visit (cold @ 08-12 07:00 -> t_end 19:00, hold @ t0 18:00,
  12 sim-h, 49 frames): **282.9 min** (16 973 s wall)
- catch-up visit (junction 18:00 -> t0 19:00 -> t_end 08-13 07:00,
  13 sim-h incl. the full 12 h prediction tail, 53 frames):
  **316.7 GPU-min** (19 001 s wall)

Both numbers were measured while the live P1 worker solved a 13.4 M-cell
episode (`2026081415_03349000`) on the same card for the whole run, so
they are ~2x upper bounds. Normalised to the P1 solo throughput reference
(6.7e7 cell-steps/s; 24 sim-h full basin = 15 824 s = 264 min, i.e.
~11 min per sim-h at 4.67 M cells) a solo catch-up visit is ~145-160
GPU-min, inside the brief's 12-25 GPU-min-per-event-hour expectation
(13 sim-h -> 156-325) and ~55-60 % of the classic P1 cost of returning to
an episode (full 24 sim-h re-solve, 264 min solo). The anchored visit
costs the same as a classic anchored solve of the same span (it IS one),
so the win is entirely on revisits, which is what the scheduler
interleaves.

## Checklist extras

- **Cross-validation at real-forcing window scale** (independent
  same-design implementation, branch `p16-local-impl`, real EF5 bundle,
  632x632 window): continuation bit-identical to continuous (J 1.0000,
  0.000 cm at mid and final); interleave bit-exact with fully contiguous
  15-min frame records for both events; restart J 0.9990 / 1.22 cm.
  Two implementations of the brief's design converging to the same
  numbers on real forcing corroborates the synthetic gates.
- `gpu_worker_space/chunkrun.py` referenced by the brief does not exist in
  any reachable repo (CREST_demo, stem_worker, CREST_AI searched); the
  session API was factored from `run_event` instead.

## Dependencies for the flip

1. **Carry-forward publish**: incremental visits require the
   `publish_event` that keeps frames strictly before the increment's
   `sim_start`. That code exists only in the DEPLOYED Space's `hf_data`
   (synced to `$SCRATCH/crest_worker/space_ref`); the GitHub CREST_AI
   clone predates it. `CREST_AI_DIR` must point at the synced copy
   (re-sync before the flip — V30 provenance stamps landed Space-side).
2. **Standing rules** (re-affirmed by the user 2026-08-14, enforced in
   `107c8187`): hygiene never sweeps queue entries < 48 h old or holding
   a fresh claim (the worker has no sweeper; rule binds future scripts);
   `_spec_unchanged` is re-checked immediately BEFORE `publish_event` in
   both worker paths, not only before consuming; tokens are never
   printed or logged.
3. RAM per parked session at 4.7 M cells: 4 fp32 grids (h, qx, qy,
   maxdepth) ~= 75 MB; `--max-sessions 6` ~= 450 MB — fine on this node.
