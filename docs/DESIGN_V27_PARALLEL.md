# V27 — Full-basin native-resolution events: parallel & GPU design

Status: DESIGN (2026-08-12). Follows the V25 resolution-first policy:
resolution is fixed at the DEM's native cell size and is never coarsened;
when the basin exceeds the cell budget the window shrinks. V27 removes the
window limit so events cover the FULL basin at native 30 m (and 10 m where
it matters), using the resources actually available: Hugging Face Spaces
and a single-node GPU HPC.

## 1. Problem size

| Domain | @30 m (1") | @10 m (1/3") |
|---|---|---|
| Small basin (0.14°, ~15 km) | 0.25 M cells | 2.3 M |
| Youghiogheny box (0.85°, ~95 km) | 10 M | 92 M |
| Event window today (V25 CPU) | 0.4 M | — |

A 24 h event at 30 m needs dt ≈ 1–3 s (CFL, deep channel c=√(gh)≈10 m/s):
~30–80 k steps. Work ≈ cells × steps:

- Youghiogheny @30 m: ~5×10¹¹ cell-steps
- Youghiogheny @10 m: ~1.4×10¹³ cell-steps (dt shrinks 3×)

## 2. Throughput reality (what each resource can do)

The solver is a memory-bandwidth-bound stencil. Reference points: this
solver does ~1.2 steps/s at 1 M cells on a laptop CPU (~10⁶ cell-steps/s
effective per core-set); Inunda measured ~11.5 k steps/s at 1.2 M cells on
a B200 (~1.4×10¹⁰ cell-steps/s). An A100/V100-class card lands at
~3–7×10⁹ cell-steps/s; even a consumer 4090 ~2–4×10⁹.

Consequences:

- **CPU Space** (today): 0.4 M cells is the honest ceiling per hourly tick.
- **One HPC GPU**: Youghiogheny @30 m ≈ **2–10 minutes**; @10 m ≈
  **1–3 hours**. Memory is a non-issue (state = ~6 arrays × N × 4 B;
  92 M cells ≈ 2.2 GB).
- **The single-node HPC is not a limitation — it is the workhorse.** One
  GPU covers full-basin 30 m for every event we have seen, and 10 m for
  the events that deserve it. Multi-node MPI only becomes necessary beyond
  ~10⁸ cells (Harvey-scale megaflood domains at 10 m).

## 3. Architecture: three tiers, one storefront

Everything still publishes to the same `events/<id>/` layout in
CREST_data; the dashboard does not change.

```
trigger (Space, hourly tick)
  ├── EF5 nowcast run (Space, cheap): runoff/streamflow grids @3"
  ├── job bundle -> events/queue/<id>.json + forcing.tar (few MB)
  │
  ├── [T2] HPC GPU worker claims job ── full basin, native res ──┐
  │        (single GPU; no decomposition needed < ~10^8 cells)   │
  ├── [T3] same worker, multi-GPU in the node ── subbasin        ├─> frames,
  │        decomposition + ghost-cell halo (torch.distributed)   │   maxdepth,
  │                                                              │   manifest
  └── [T1] fallback: CPU Space windowed run (V25, unchanged) ────┘
           if no worker claims the job within EVENT_CLAIM_MIN
```

Key split: **EF5 + forcing prep stay on the Space** (next to the data);
**only the solver** — the actual bottleneck — moves to the GPU. The job
bundle carries the EF5 grids (3", few MB compressed), gauge/trigger
metadata, and the domain spec; the worker fetches its own 3DEP DEM tiles
(cached on scratch).

## 4. Tight coupling: subbasin decomposition + ghost-cell halo (T3)

Per user directive: decompose by SUBBASINS, exchange ghost cells so the
FULL shallow-water dynamics (including backwater) couple across ranks.

- **Partition**: subcatchments from EF5's FAM (or HydroBASINS lev08)
  grouped into per-rank tiles, balanced by historically-wettable cell
  count (channel + low-lying cells), not raw area. Each rank owns a
  rectangular bounding tile plus an ownership mask.
- **Halo width = 2 rings** — exactly the MUSCL stencil the solver's
  two-ring padding (`_sympad`/`_reppad`) already assumes. The halo slots
  in where boundary padding sits today, so the solver change is localized:
  `pad()` becomes `exchange_or_pad()`.
- **What is exchanged**: h, qx, qy after **each SSP-RK2 stage** (2
  exchanges/step). Bed elevation z exchanged once at setup. Because the
  hydrostatic reconstruction is face-local, both ranks compute the shared
  face flux from identical stencil data -> identical flux -> exact mass
  conservation and the C-property survive decomposition bit-for-bit.
- **Global dt**: allreduce(min) of local CFL dt each step.
- **Transport**: `torch.distributed` with NCCL inside the node (P2P over
  NVLink/PCIe). No MPI library needed for a single node; the same code
  runs multi-node later with an MPI/NCCL backend if a cluster appears.
- Halo traffic per step is tiny (2 rings × tile edge × 3 vars × 4 B ≈ a
  few hundred KB) — negligible against NVLink; this scales.

## 5. Why Spaces do NOT tightly couple (honest math)

Ghost-cell exchange needs 2 messages/step × 30–80 k steps. Space-to-Space
HTTP RTT is ~50–200 ms => 1–9 hours of pure latency per simulated day —
before any compute. Therefore:

- **Spaces parallelize EVENTS, not one domain**: N runner Spaces each
  claim whole jobs from the queue (embarrassingly parallel; useful when
  several basins flood at once).
- Cross-machine domain splits, if ever needed, use **loose one-way
  nesting at subbasin outlets**: downstream rank takes the upstream
  rank's routed discharge as a channel-stage boundary — exactly the EF5
  channel-stage coupling V25 already ships. Approximation: no backwater
  across the cut; acceptable at true subbasin outlets, and stated in the
  manifest when used.

## 6. Job queue protocol (minimal, HF-native)

- `events/queue/<id>.json`: domain spec, t0/window, forcing paths, res.
- Claim = worker commits `events/queue/<id>.claim` with its identity +
  heartbeat timestamp; re-claimable when the heartbeat goes stale.
- Result = normal `publish_event` commit; the tick sees the published
  manifest and skips its own T1 fallback.
- The T1 fallback keeps the system autonomous when the HPC is down,
  drained, or in maintenance — no operational dependency on the worker.

## 7. Latency risk & the degradation ladder (safeguards)

The HPC is a shared, single-node resource that WILL be down sometimes
(maintenance, scratch purges, preemption, the GPU busy with DI-LSTM
training, token expiry). The system is designed so no HPC failure mode can
delay an event by more than minutes, and none can lose an event:

- **The Space never blocks on any worker.** `EVENT_QUEUE_MODE` is
  `off` / `shadow` (enqueue + still solve locally) / `on` (queue-first with
  bounded waits). All waits are capped: `EVENT_CLAIM_WAIT_S` (default
  300 s) for a claim, `EVENT_RESULT_WAIT_S` (default 2700 s) for the
  result — and the result wait ABORTS EARLY if the worker's claim
  heartbeat goes stale, so a worker that dies mid-run costs roughly one
  heartbeat-staleness window (~10 min), not the full timeout.
- **Worst-case timelines vs today** (mode `on`): HPC completely absent →
  event map arrives 5 min later than today via the CPU window; worker
  crashes mid-run → ~10-15 min later; worker healthy → full-basin native
  result typically FASTER than the CPU window finishes.
- **The ladder of claimants** (the protocol in Sec. 6 is worker-agnostic —
  a claimant is anything that commits a `.claim` and publishes results):
  1. **HPC single GPU** (primary): full-basin 30 m in minutes, 10 m in
     1-3 h.
  2. **ZeroGPU worker Space** (P1.5 backup): same worker code on an HF
     ZeroGPU Space, integration chunked into `@spaces.GPU` slices
     (~60-120 s each) with (h, qx, qy) held in Space RAM between slices.
     Covers full-basin 30 m in ~10-30 wall-clock min (slice queuing under
     load); 10 m runs exceed ZeroGPU quotas and remain HPC-only. It only
     claims jobs the HPC has left unclaimed for a grace period, so the
     two never race.
  3. **CPU window (T1)** — the unconditional floor: today's V25 product,
     windowed native-resolution, needs nothing but the Space itself.
- **Capacity honesty**: a worker must NOT claim a job whose native-res
  cell count exceeds what it can hold (resolution is never coarsened —
  standing directive). An oversized/unclaimable job simply falls through
  the ladder to the CPU window; nothing hangs, nothing degrades silently.
- **Queue hygiene**: every enqueue sweeps bundles older than 48 h, and
  failed jobs are converted to `<id>.failed.json` so the queue never
  wedges on a poison job.

## 8. Build phases

- **P1 — HPC single-GPU worker** (biggest ROI, no decomposition):
  queue protocol + worker daemon (systemd/cron on the login-adjacent
  node, same HF-token pattern as the DI-LSTM training) + forcing-bundle
  loader in `crestimap`. Full-basin 30 m for every event; 10 m on demand.
  Executable contract: `docs/P1_WORKER_BRIEF.md`.
- **P1.5 — ZeroGPU backup worker**: the same worker loop deployed to a
  ZeroGPU Space with chunked GPU slices (ladder rung 2 above). Built on
  the Space side once P1's worker code exists to reuse.
- **P2 — multi-GPU halo** (only if the node has >1 GPU): partition
  module + `exchange_or_pad()` + allreduce dt; validate C-property, mass,
  and bit-consistency against single-GPU runs.
- **P3 — runner-Space fleet**: dispatcher assigns queued events to N
  duplicate runner Spaces for concurrent-event bursts.

## 9. Validation gates

1. P1 worker reproduces a V25 windowed event (same window/res) within
   float tolerance.
2. Full-basin 30 m Youghiogheny event: mass balance < 1e-8, wet frames
   published end-to-end, runtime logged.
3. P2: 2-GPU vs 1-GPU identical results (same dt sequence) on a synthetic
   dambreak crossing the partition boundary and on a real event.
4. Harvey/Brays Bayou hindcast at 10 m vs v1 results + USGS HWMs (the
   standing validation milestone) becomes feasible at T2/T3.
