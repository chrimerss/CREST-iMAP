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

## Status 2026-08-14: IMPLEMENTED — your job is CUDA validation + the flip

The design above is now code on this branch; `git pull` and validate.

- `crestimap/session.py` — `EventSession`. One refinement over the sketch:
  each visit holds a **junction snapshot** (state captured exactly at the
  bundle's t0). The [t0, t_end] prediction tail is published, then the
  state AND the obs-supported maxdepth roll back to the snapshot, so a
  stale tail's over-prediction never leaks into later publishes. Each
  visit also re-emits the held state as its first frame: publish
  carry-forward keeps only frames strictly BEFORE sim_start, so without
  the re-emit the junction frame would vanish — and it is the frame
  restart recovery (`init_depth`, hierarchy level 2) needs.
- `crestimap/worker.py` — `run_sessions()` scheduler exactly as specified
  (catch-up bundles outrank new events; claims held only while a visit is
  advancing; eviction on `status=="ended"` in events/index.json, idle
  > `--evict-idle-h` (12 h), LRU past `--max-sessions` (6)). **OFF by
  default**: the classic loop is untouched until you pass `--sessions`
  (or `EVENT_SESSIONS=1`, see run_worker.sh).
- `crestimap/tests/test_session.py` — gates 1, 2, 4 on synthetic data.
  CPU results (2026-08-14): gate 1 wet Jaccard 1.0000, mean wet |Δ|
  0.00 cm; gate 2 bit-exact both events; gate 4 Jaccard 0.9974,
  0.36 cm. (~90 min on a laptop CPU — minutes on your card.)
- The ZeroGPU backup Space already runs `EventSession` (claim-less shadow,
  sessions resident across bundles) — protocol compatibility is exercised
  from both sides.

Your checklist, in order:
1. `git pull`, run the full suite with `CRESTIMAP_TEST_DEVICE=cuda`
   (test_session.py included) and record the numbers.
2. Gate 3: run `--sessions --no-publish --once` style visits against a
   real queued episode and report GPU-minutes for (a) the first anchored
   visit and (b) a catch-up visit at ~4.7 M cells.
3. Write GO/NO-GO + all numbers to `docs/P1_6_VALIDATION.md`, push to v2.
4. On GO and user confirmation: restart the worker with
   `EVENT_SESSIONS=1 ./run_worker.sh --publish`.

Standing rules still apply: never sweep queue entries younger than 48 h or
holding a fresh claim; re-check `_spec_unchanged` before publishing; never
print the HF token; push only to this fork's `v2`.
