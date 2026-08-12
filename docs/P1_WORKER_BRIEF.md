# V27 P1 — GPU event-worker brief (for Claude Code on the HPC)

You are building the single-GPU inundation worker specified in
`docs/DESIGN_V27_PARALLEL.md` (read Sections 2, 3, 6, 7 first). This
document is the executable contract; together with the code in this repo
and the CREST_AI clone it is self-contained. Environment/token mechanics
are the same as the DI-LSTM work (`CREST_AI/nowcast_space/README_HPC.md`).

The Space side is already LIVE in **shadow mode**: every real 2-D
inundation event the dashboard triggers also publishes a job bundle under
`events/queue/` in the `vincewin/CREST_data` dataset, while the Space
still solves its own CPU window. You can develop and validate against real
bundles from day one without being a dependency for anything.

## What you are building

1. `crestimap/worker.py` — a daemon that polls the queue, claims a job,
   downloads its EF5 forcing bundle, runs the FULL-BASIN native-resolution
   solve on the GPU, renders/publishes results in exactly the V25 layout
   (reusing CREST_AI's own functions — do not reimplement rendering or
   publishing), and cleans up the queue entry.
2. `run_worker.sh` — nohup wrapper in the style of
   `nowcast_space/run_train.sh` (survives SSH disconnect, logs to
   `worker.log`), or a SLURM long-runner if this cluster requires it.

Code lives in THIS repo (the CREST-iMAP fork), branch `v2`. **Pushing your
worker code and any GPU fixes to this branch IS part of the job** (unlike
the retraining brief). Never push to CREST_AI.

## Hard rules

- **Do NOT publish to `events/` until the user flips the Space to
  `EVENT_QUEUE_MODE=on`.** Until then always run with `--no-publish`:
  write results locally and validate against the Space's own published
  event (same id). In shadow mode the Space also solves locally — a worker
  publish would fight it for the same event folder.
- **Never print or log the HF token** (`~/huggingface.txt`).
- Claim before working, heartbeat while working, clean up after. Never
  delete anything outside `events/queue/`, and (once publishing is
  enabled) touch `events/<id>/` only via `publish_event`.
- **Resolution is never coarsened** (standing user directive). If the
  basin bbox at native resolution exceeds `EVENT_MAX_CELLS_GPU`, do NOT
  claim the job (the Space falls back to its windowed CPU run). Note:
  `crestimap.dem.load_dem` will silently block-mean if `max_cells` is
  exceeded — your pre-claim size check is what prevents that path from
  ever engaging. Compute expected cells from the bbox and
  `DEM_RES_DEG = {"1": 1/3600, "13": 1/10800}` before claiming.
- One job at a time; long runs detached (nohup/SLURM), never attached to
  your own process.
- Don't touch the nowcast model/data repos at all.

## Repos and code reuse

```bash
git clone -b v2 https://github.com/mchen15ouedu/CREST-iMAP.git   # this repo
git clone https://github.com/mchen15ouedu/CREST_AI.git           # reuse only, never push
pip install -e ./CREST-iMAP                                      # crestimap package
```

Reuse table — the worker should be mostly glue:

| Need | Use (do not rewrite) |
|---|---|
| Solve | `crestimap.EventConfig` / `run_event` (`event.py`) |
| DEM | fetched inside `run_event` via `crestimap.dem` (3DEP S3; cache on scratch) |
| Episode archive merge + maxdepth | `CREST_AI/hf_data/eventsim.py::_update_archive` |
| PNG overlays + adaptive color cap | `eventsim._make_pngs` / `eventsim.adaptive_cap` |
| Publish (one batched commit + retention) | `CREST_AI/hf_data/eventstore.py::publish_event` |

Import pattern (hf_data has no `__init__.py`; it works as a namespace
package from the repo root):

```python
sys.path.insert(0, "/path/to/CREST_AI")
from hf_data import eventsim, eventstore
```

`eventsim`/`eventstore` import heavy deps lazily inside functions, so this
pulls in nothing Space-specific. `_update_archive` and `publish_event`
read `HF_TOKEN` from the environment — export it before running.

## Step 0 — access check (do this first)

The HPC token was scoped for the nowcast repos; verify it can WRITE the
`vincewin/CREST_data` dataset before building anything: commit a tiny probe
file to `events/queue/.probe`, then delete it. If either operation returns
403, STOP and report — the user must extend the token's scope; there is no
workaround you should attempt.

## Environment

The `nowcast` conda env plus: `pip install rasterio pillow pyarrow`.
Torch with CUDA is already there from training. Set:

```bash
export HF_TOKEN=$(tr -d ' \r\n' < ~/huggingface.txt)
export EVENT_DEM_CACHE=/media/scratch/$USER/dem_cache   # 10 m tiles are ~400 MB each
```

Outbound HTTPS needed: `huggingface.co` and `prd-tnm.s3.amazonaws.com`
(3DEP DEM tiles). If compute nodes are offline, warm the DEM cache from
the login node like the HF cache.

## Queue protocol (the contract — mirror it exactly)

Files under `events/queue/` in `vincewin/CREST_data` (dataset):

| File | Writer | Meaning |
|---|---|---|
| `<id>.json` | Space | job spec (fields below) |
| `<id>.forcing.tar.gz` | Space | every EF5 output `.tif` for the window — extract to a dir and pass it as `ef5_output_dir`; `run_event` parses the `q.*`/`runoff.*`/`subrunoff.*` names itself |
| `<id>.claim` | worker | `{"worker": "<host>:<pid>", "hb": "YYYY-MM-DDTHH:MM:SSZ"}` |
| `<id>.failed.json` | worker | short error report; job consumed |

- Poll `list_repo_files` every ~60 s for `<id>.json` entries with no claim
  or a STALE claim (heartbeat older than 600 s). Claim the oldest by
  committing `<id>.claim`; re-commit it with a fresh `hb` at least every
  240 s while working (the Space treats >600 s as dead and falls back —
  a lazy heartbeat wastes GPU work).
- Hourly episode re-simulations REPLACE `<id>.json`/`<id>.forcing.tar.gz`
  under the same id and delete your old claim — always claim against the
  current spec's `queued` timestamp, and if the spec changes under you
  mid-run, finish and let the next poll pick up the newer one.
- On success (publishing enabled): `publish_event(out_dir, manifest)`,
  then one small commit deleting `<id>.json` + `<id>.forcing.tar.gz` +
  `<id>.claim`.
- On failure: commit `<id>.failed.json` (exception + traceback tail — no
  token, no paths containing secrets) and delete the spec/tar/claim in the
  same commit, so the queue never wedges on a poison job. The Space's
  48-h sweep is the backstop, not the plan.
- Commit budget is account-wide 256/h; your steady state (claim +
  heartbeats every 4 min + publish + cleanup) is well inside it.

## Job spec fields

```json
{"event_id": "2026081113_03081000", "episode": true,
 "gauge": {"id": "03081000", "lat": 39.86, "lon": -79.29, "area_km2": 1366.0},
 "bbox_basin":  [w, s, e, n],      // YOUR domain: the full basin
 "bbox_window": [w, s, e, n],      // the Space's cropped CPU window (validation)
 "t0": "...", "t_end": "...", "sim_start": "...",   // %Y-%m-%dT%H:%MZ
 "model": "crest",                 // EF5 output naming -> EventConfig.model
 "dem_res": "1",                   // "1"=30 m; "13"=10 m only when user asks
 "trigger": {...}, "hydro": [...], "basin": [[lat,lon],...] | null,
 "queued": "%Y-%m-%dT%H:%M:%SZ"}
```

## Execution recipe (per job)

```python
cfg = EventConfig(
    event_id=spec["event_id"], bbox=tuple(spec["bbox_basin"]),
    t0=..., t_end=..., sim_start=...,          # parse the spec times
    ef5_output_dir=extracted_tar_dir, out_dir=local_out,
    model=spec["model"], dem_res=spec["dem_res"],
    dem_cache=os.environ["EVENT_DEM_CACHE"],
    max_cells=int(os.environ.get("EVENT_MAX_CELLS_GPU", "100000000")),
    trigger=spec["trigger"], device="cuda", progress=log)
manifest = run_event(cfg)
# then EXACTLY the tail of eventsim.run_one:
manifest["gauge"] = spec["gauge"]["id"]
manifest["hydro"] = spec["hydro"]
manifest["status"] = "active"
manifest["basin"] = spec["basin"]
eventsim._update_archive(cfg.out_dir, manifest, log)   # merges the episode's prior archive from HF
if not manifest.get("archive_frames"):
    manifest["status"] = "ended"; manifest["dry"] = True
eventsim._make_pngs(cfg.out_dir, manifest)             # adaptive cap + manifest rewrite
ok = eventstore.publish_event(cfg.out_dir, manifest)   # ONLY after the mode flip
```

## GPU validation gates (in order, before reporting done)

The solver (`crestimap/solver.py`) is device-agnostic torch but has only
ever run on CPU. Expect small device bugs (tensor placement in
`forcing.py` regridding is the likely spot); fixing them in this repo is
in scope — push fixes with clear messages.

1. **Unit tests on CUDA**: run `crestimap/tests` with the device switched
   to cuda (lake-at-rest / C-property and dambreak must pass as on CPU).
2. **Mass conservation on CUDA**: synthetic dambreak, `bc="wall"`, no
   nudge, no rain — relative volume drift < 1e-6 over the run.
3. **Shadow-job replay, CPU vs CUDA vs the Space**: take a real bundle,
   run it at the SPACE's config (`bbox_window`, `max_cells=400000`, same
   `dem_res`) on cpu and on cuda; download the Space's published
   `events/<id>/` frames for the same id. For each pair: per-frame
   wet-area Jaccard >= 0.95 and mean |Δdepth| over the wet union < 2 cm
   (frames are uint16 centimeters — 1 cm is quantization).
4. **Full-basin 30 m run**: same bundle at `bbox_basin` on cuda. Log grid
   size, step count, wall-clock, and cell-steps/s. Target >= 1e9
   cell-steps/s on an A100-class card. If you land far below, the likely
   cause is the per-step `.item()` host sync in `compute_dt`; recomputing
   dt every k steps with a 0.9 safety factor on the held value is an
   acceptable optimization — validate gates 1-3 still pass after.

## Report back

Gauge everything against the design doc's throughput table. In your final
summary: the probe-write result, gates 1-4 numbers (tolerances, Jaccard,
throughput, wall-clock for window + full basin), any device fixes pushed,
worker/daemon start command, and a clear GO / NO-GO for the user to flip
`EVENT_QUEUE_MODE=on`. Do not flip anything yourself — the mode is a Space
environment variable only the user (or the laptop Claude) changes.

## Explicitly out of scope for P1

Multi-GPU halo exchange (P2), the ZeroGPU backup worker (P1.5, built
Space-side), 10 m runs as a default (only when the user asks per event),
and any change to trigger logic, EF5, or the dashboard.
