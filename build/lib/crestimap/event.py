"""Event-triggered 2-D inundation simulation for the CREST-AI coupling.

Trigger flow (CREST-AI side, hf_data/eventsim.py):

 1. The hourly nowcast risk layer flags gauges at tier 3 ("flood": next-6-h
    AI peak >= Q5); hotspot clusters pick the trigger gauges.
 2. The event domain is the triggered basin's bbox; EF5 runs the window
    [t0 - hindcast, t0 + horizon] in nowcast mode (upstream obs + DI-LSTM
    injection) with output_grids=streamflow|runoff|subrunoff.
 3. run_event() below: 3DEP DEM (fetched on demand, no HF archive),
    EF5 runoff grids as lateral inflow, channel pre-wetting from the 2-D Q
    grid, well-balanced solver integration, compact depth frames out.
 4. The caller publishes cfg.out_dir as ONE batched commit (eventstore).
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import os


@dataclasses.dataclass
class EventConfig:
    event_id: str                       # e.g. "2026081018_07332500"
    bbox: tuple                         # (w, s, e, n) lon/lat
    t0: datetime.datetime               # nowcast issue time (UTC)
    t_end: datetime.datetime            # nowcast horizon end
    ef5_output_dir: str                 # q./runoff./subrunoff. GeoTIFF stacks
    out_dir: str                        # local results dir (published as one commit)
    model: str = "crest"                # EF5 output-file naming
    sim_start: datetime.datetime = None # default t0 - 6 h (channel fill-in)
    dem_path: str = None                # pre-clipped DEM; if None fetch 3DEP
    dem_res: str = "1"                  # "1"=1" (~30 m, CPU), "13"=1/3" (~10 m, GPU)
    dem_cache: str = "dem_cache"
    max_cells: int = 400_000            # CPU-feasible ceiling; raise on GPU
    n_manning: float = 0.05
    q_channel_min: float = 5.0          # m3/s: EF5 cells >= this pre-wet as channel
    output_every_s: float = 900.0       # depth-frame cadence
    trigger: dict = None                # provenance: gauge id / tier / hotspot
    device: str = "cpu"
    dt_every: int = 1                   # CFL recompute cadence (GPU: ~10)
    progress: object = None             # optional callable(str)


def run_event(cfg: EventConfig) -> dict:
    """Run the hydrodynamic event simulation; returns the manifest dict.

    Writes to cfg.out_dir: depth_<YYYYMMDDHHMM>.tif frames (uint16 cm,
    deflate), maxdepth.tif, dem.tif (clipped, for reproducibility) and
    manifest.json.
    """
    import numpy as np
    import torch
    from . import dem as demmod
    from . import io as iomod
    from .forcing import (EF5ChannelStage, SolverGrid, ef5_forcing,
                          initial_state_from_ef5, parse_ef5_dir,
                          regrid_to_solver)
    from .solver import SWESolver

    say = cfg.progress or (lambda s: None)
    os.makedirs(cfg.out_dir, exist_ok=True)
    dtype = torch.float32

    # ---- terrain -------------------------------------------------------- #
    if cfg.dem_path:
        grid = SolverGrid.from_dem(cfg.dem_path, dtype=dtype, device=cfg.device)
    else:
        say(f"fetching 3DEP DEM (res {cfg.dem_res}) for {cfg.bbox}")
        z, tr, crs = demmod.load_dem(cfg.bbox, cfg.dem_res, cfg.dem_cache,
                                     cfg.max_cells)
        grid = SolverGrid.from_array(z, tr, crs, dtype=dtype, device=cfg.device)
    ny, nx = grid.z.shape
    say(f"solver grid {ny}x{nx} ({ny * nx / 1e3:.0f}k cells, "
        f"dx~{grid.dx:.0f} m)")
    iomod_dem = os.path.join(cfg.out_dir, "dem.tif")
    _write_dem(iomod_dem, grid)

    # ---- forcing + initial conditions ----------------------------------- #
    sim_start = cfg.sim_start or (cfg.t0 - datetime.timedelta(hours=6))
    rain = ef5_forcing(cfg.ef5_output_dir, grid, sim_start, model=cfg.model,
                       dtype=dtype, device=cfg.device)
    h0 = torch.zeros_like(grid.z)
    qx0 = torch.zeros_like(grid.z)
    qy0 = torch.zeros_like(grid.z)
    qs = parse_ef5_dir(cfg.ef5_output_dir, "q", cfg.model)
    if qs:
        import rasterio
        t_near, path = min(qs, key=lambda tp: abs((tp[0] - sim_start)
                                                  .total_seconds()))
        with rasterio.open(path) as ds:
            src = ds.read(1).astype(float)
            if ds.nodata is not None:
                src = np.where(src == ds.nodata, 0.0, src)
            qg = regrid_to_solver(np.clip(src, 0, None), ds.transform,
                                  (ny, nx), grid.transform, ds.crs, grid.crs)
        h0, qx0, qy0 = initial_state_from_ef5(qg, None, grid.z, grid.dx, grid.dy)
        h0 = h0.to(dtype=dtype, device=cfg.device)
        h0 = torch.where(torch.as_tensor(qg, device=cfg.device) >=
                         cfg.q_channel_min, h0, torch.zeros_like(h0))
        qx0 = torch.zeros_like(h0)
        qy0 = torch.zeros_like(h0)
        say(f"channel pre-wet from q grid @ {t_near:%Y-%m-%d %H:%M} "
            f"({int((qg >= cfg.q_channel_min).sum())} channel cells)")

    # warm continuation: the caller may drop the episode's previous depth
    # field into the forcing dir as `init_depth_<YYYYMMDDHHMM>.tif` (uint16
    # cm, any grid — regridded here). It is applied ONLY when its valid time
    # matches this run's sim_start (±90 min): the same bundle serves both a
    # fresh-slice continuation (times match -> inherit the water) and an
    # anchored full-window re-solve (times differ -> ignore it; injecting a
    # later state at the window start would plant future water in the past).
    # h0 = max(channel pre-wet, previous depth); momentum restarts at rest.
    import glob as _glob
    for init_path in _glob.glob(os.path.join(cfg.ef5_output_dir,
                                             "init_depth_*.tif")):
        try:
            ts = os.path.basename(init_path)[11:-4]
            t_init = datetime.datetime.strptime(ts, "%Y%m%d%H%M")
        except ValueError:
            continue
        if abs((t_init - sim_start).total_seconds()) > 5400:
            say(f"init_depth @{t_init:%m-%d %H:%M} != sim_start "
                f"{sim_start:%m-%d %H:%M} — ignored (anchored re-solve)")
            continue
        import rasterio
        with rasterio.open(init_path) as ds:
            prev = ds.read(1).astype(float) / 100.0          # cm -> m
            if ds.nodata is not None:
                prev = np.where(prev == ds.nodata / 100.0, 0.0, prev)
            prev = regrid_to_solver(np.clip(prev, 0, None), ds.transform,
                                    (ny, nx), grid.transform, ds.crs,
                                    grid.crs)
        prev_t = torch.as_tensor(prev, dtype=dtype, device=cfg.device)
        h0 = torch.maximum(h0, prev_t)
        say(f"warm continuation from {os.path.basename(init_path)} "
            f"({int((prev_t > 0.02).sum())} wet cells carried over)")

    # routed-flood coupling: EF5's hourly discharge grids drive the channel
    # stage all through the run (recession events carry their water in the
    # routed network, not the local runoff grids — without this, an event
    # triggered days after the rain simulates dry)
    nudge = None
    try:
        nudge = EF5ChannelStage(cfg.ef5_output_dir, grid, sim_start,
                                model=cfg.model, q_min=cfg.q_channel_min,
                                dtype=dtype, device=cfg.device)
        # diagnose the raw EF5 q grid before trusting the coupling
        import rasterio as _rio
        _, qp = nudge.series[nudge._index(0.0)]
        with _rio.open(qp) as ds:
            qsrc = ds.read(1).astype(float)
            if ds.nodata is not None:
                qsrc = np.where(qsrc == ds.nodata, np.nan, qsrc)
        say(f"q grid {os.path.basename(qp)}: src max {np.nanmax(qsrc):.2f} m3/s, "
            f"src cells>= {cfg.q_channel_min}: {int(np.nansum(qsrc >= cfg.q_channel_min))}, "
            f"shape {qsrc.shape}")
        st = nudge.stats(0.0)
        say(f"channel coupling: {st['channel_cells']} channel cells on solver "
            f"grid, max stage {st['max_stage_m']:.2f} m at sim start")
    except Exception as e:
        say(f"channel coupling unavailable ({type(e).__name__}: {e})")

    # ---- integrate ------------------------------------------------------ #
    solver = SWESolver(grid.z, dx=grid.dx, dy=grid.dy, n_manning=cfg.n_manning,
                       order=2, bc="open")
    t_total = (cfg.t_end - sim_start).total_seconds()
    maxdepth = h0.clone()
    frames = []
    state = {"next": cfg.output_every_s}

    def cb(t, h, qx, qy):
        nonlocal maxdepth
        maxdepth = torch.maximum(maxdepth, h)
        if t + 1e-6 >= state["next"] or t >= t_total - 1e-6:
            when = sim_start + datetime.timedelta(seconds=round(t))
            fname = f"depth_{when:%Y%m%d%H%M}.tif"
            iomod.write_depth(os.path.join(cfg.out_dir, fname),
                              h.detach().cpu().numpy(), grid.transform, grid.crs)
            frames.append({"t": when.strftime("%Y-%m-%dT%H:%MZ"), "file": fname})
            say(f"frame {fname} (sim t={t / 3600:.2f} h)")
            while state["next"] <= t + 1e-6:
                state["next"] += cfg.output_every_s

    say(f"integrating {t_total / 3600:.1f} h "
        f"({sim_start:%m-%d %H:%M} -> {cfg.t_end:%m-%d %H:%M} UTC)")
    if nudge is not None:
        h0 = nudge(0.0, h0)               # channel water present from t=0
    solver.run(h0, qx0, qy0, t_end=t_total, rain_fn=rain, callback=cb,
               nudge_fn=nudge, dt_every=cfg.dt_every)

    iomod.write_depth(os.path.join(cfg.out_dir, "maxdepth.tif"),
                      maxdepth.detach().cpu().numpy(), grid.transform, grid.crs)
    manifest = {
        "event_id": cfg.event_id, "bbox": list(cfg.bbox),
        "t0": cfg.t0.strftime("%Y-%m-%dT%H:%MZ"),
        "sim_start": sim_start.strftime("%Y-%m-%dT%H:%MZ"),
        "t_end": cfg.t_end.strftime("%Y-%m-%dT%H:%MZ"),
        "model": cfg.model, "trigger": cfg.trigger,
        "grid": {"ny": ny, "nx": nx, "dx_m": round(grid.dx, 2),
                 "dy_m": round(grid.dy, 2),
                 "transform": list(grid.transform)[:6],
                 "crs": str(grid.crs) if grid.crs else None},
        "n_manning": cfg.n_manning, "frames": frames,
        "maxdepth": "maxdepth.tif", "dem": "dem.tif",
        "generated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(os.path.join(cfg.out_dir, "manifest.json"), "w") as fp:
        json.dump(manifest, fp)
    say("event simulation complete")
    return manifest


def _write_dem(path, grid):
    import rasterio
    z = grid.z.detach().cpu().numpy().astype("float32")
    with rasterio.open(path, "w", driver="GTiff", height=z.shape[0],
                       width=z.shape[1], count=1, dtype="float32",
                       crs=grid.crs, transform=grid.transform,
                       compress="deflate", predictor=3, tiled=True) as ds:
        ds.write(z, 1)
