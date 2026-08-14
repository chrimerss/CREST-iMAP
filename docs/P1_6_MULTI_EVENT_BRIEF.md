# P1.6 — Multi-event worker: resident sessions + cooperative scheduling

**For:** the HPC Claude Code operating `crestimap/worker.py` (you built P1; this
extends it). Same ground rules as `P1_WORKER_BRIEF.md`: push only to this
fork's `v2`, never to CREST_AI; never print the HF token.

## The directive (user, 2026-08-14)

> Workers are able to work on the next event even when the previous event is
> still waiting for the next hour to come. Worker has done all the simulation
> for event A (still active, flow near peak) but new forcing has not yet been
> downloaded — during this waiting time the worker works on B, C, D, E in the
> queue, then comes back to A when new forcing arrives, and keeps going.

## Why this is a large win

Today one claim = one blocking anchored solve. Returning to an active episode
re-simulates from trigger−12 h: hours of GPU for one new hour of information.
With a RESIDENT SESSION per event — solver state `(h, qx, qy, t)` held between
visits — a catch-up visit integrates only:

    [last obs-supported junction  ->  new t0 + horizon]   (~13 sim-h)

i.e. ~12–25 GPU-minutes per event per hour on your card. One GPU then
sustains ~3–5 live episodes in real time instead of ~1, and B/C/D fill every
gap while A waits for forcing.

## Design

### 1. `crestimap/session.py` — the resident-session primitive (build this)

Formalize the chunk-resumable runner (see `gpu_worker_space/chunkrun.py` on
the CREST_demo Space repo — it is ~80% of this; unify rather than fork it):

```python
class EventSession:
    # created on first visit to an event
    def __init__(self, cfg: EventConfig): ...        # grid, forcing, pre-wet
    def advance(self, forcing_dir, t_end) -> manifest_frames:
        """Integrate from held state to t_end using the NEW bundle's forcing.
        Re-integrates the prediction tail: hold state at the last
        OBS-SUPPORTED time (the bundle's t0), not at t_end — the [t0, t0+12]
        tail is cheap and must be re-done each visit with fresh obs."""
    def park(self): ...                              # tensors -> CPU RAM
    def state_time(self) -> datetime: ...
```

State hierarchy (exactness order):
1. **Session state in RAM** — exact continuation incl. momentum. Primary.
2. **`init_depth_<t>.tif` in the bundle** — depth-only warm start (momentum
   at rest), applied only when its valid time matches the resume point
   (already in `run_event`/fork HEAD — `git pull`). Use after a worker
   restart to rebuild a session without re-solving the whole episode.
3. **Cold channel pre-wet** — first visit ever.

### 2. Scheduler in `worker.py` (replace the single-job loop)

```
loop:
  for s in sessions (oldest unprocessed bundle first):
      if a NEW bundle exists for s.event (spec.queued > s.last_queued):
          claim -> download bundle -> s.advance() -> publish increment
          -> release claim -> s.park(); s.last_queued = spec.queued
  else if an unclaimed event fits the cell budget:
      claim -> new EventSession -> solve to current t_end -> publish
      -> release claim -> park
  else: sleep(poll)
```

- **Claims**: hold ONLY while actively advancing; release on park. The claim
  protocol is unchanged — events stay exclusive, other workers (ZeroGPU
  backup) can never collide.
- **Publishing an increment**: publish_event on the Space side now does
  frame carry-forward (frames older than the run's `sim_start` survive), so
  publishing just the new frames + updated manifest/archive works — set the
  increment's manifest `sim_start` to the junction time.
- **Session eviction**: episode `ended` in events/index.json, or an LRU cap
  (`MAX_SESSIONS`, suggest 6; a 4.7M-cell state is ~75 MB in RAM).
- **Restart recovery**: sessions are RAM-only. On boot, rebuild lazily via
  the bundle's `init_depth` (hierarchy level 2) — do NOT re-solve anchored
  windows unless the episode has no published frames at all.

### 3. What does NOT change

- Queue layout, claim/heartbeat/stale rules, failed.json, one-event-per-claim.
- The Space side: bundles per tick are already the right granularity; a new
  bundle for A IS the "new forcing arrived" signal.
- Never coarsen; cell-budget check before first claim of an event.

## Validation gates (report numbers before enabling by default)

1. Session-continuation equivalence: advance() through 3 successive bundles
   vs one continuous solve of the same span — wet Jaccard ≥ 0.99, mean wet
   |Δdepth| < 2 cm at the final time.
2. Interleave test: two synthetic events, alternating bundles — both records
   contiguous, no cross-contamination of state.
3. Throughput: report GPU-minutes per catch-up visit at ~4.7M cells.
4. A restart mid-episode recovers via init_depth and continues (gate 1
   tolerance vs the no-restart run).

Report GO/NO-GO + numbers in `docs/P1_6_VALIDATION.md` on `v2`.
