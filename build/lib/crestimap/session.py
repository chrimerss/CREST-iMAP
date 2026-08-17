"""P1.6 resident event sessions — solver state held between worker visits.

One EventSession per active episode. The session keeps the full solver state
(h, qx, qy — depth AND momentum) in CPU RAM while the episode waits for its
next forcing bundle, so a catch-up visit integrates only

    [last obs-supported junction  ->  new t0 + horizon]

instead of re-solving from the anchored window start (docs/
P1_6_MULTI_EVENT_BRIEF.md is the contract; the user directive of 2026-08-14
is quoted there).

Visit protocol (one visit = one queue bundle):

    s = EventSession(cfg)                    # first bundle: cold or resumed
    man = s.advance(forcing_dir, out_dir, t0, t_end, device="cuda")
    # ... park until the episode's next bundle arrives, then:
    man = s.advance(next_forcing, out2, t0_next, t_end_next, device="cuda")

Each visit integrates from the held state to t_end, but the state that is
KEPT is a snapshot taken at the bundle's t0 — the last obs-supported time.
The [t0, t_end] prediction tail is published (frames + maxdepth) and then
rolled back, so the next visit re-simulates it with fresh observations.
maxdepth is likewise split: the accumulated obs-supported maximum survives
the rollback; a stale tail's over-prediction never pollutes later publishes.

The visit manifest's sim_start is the junction this visit started from —
exactly what eventstore.publish_event's frame carry-forward expects: frames
older than sim_start survive on the store, frames >= sim_start are replaced
by this visit's fresh ones.

ZeroGPU note: chunk() is fork-safe like chunkrun.ChunkedEvent was — state
lives on CPU between chunks, and state_tuple()/set_state() let a
@spaces.GPU child return the advanced state to the parent process.
"""
from __future__ import annotations

import datetime
import glob
import json
import os

INIT_PREFIX = "init_depth_"


class EventSession:
    """Resident solver state for one episode; advance() per queue bundle."""

    def __init__(self, cfg, resume: bool = True):
        """CPU-side setup: DEM/grid + initial state.

        cfg is the FIRST bundle's EventConfig (bbox, sim_start=anchor,
        ef5_output_dir, dem/model settings). With resume=True (worker
        restart recovery, state-hierarchy level 2) the latest
        init_depth_<t>.tif in the forcing dir with t <= cfg.t0 fast-forwards
        the session to t (depth from the frame, momentum at rest) instead of
        re-solving the anchored window. resume=False always starts cold at
        cfg.sim_start (equivalence tests; brand-new episodes have no
        init_depth in the bundle, so both paths start cold there).
        """
        import numpy as np
        import torch
        from . import dem as demmod
        from .event import _write_dem
        from .forcing import (SolverGrid, initial_state_from_ef5,
                              parse_ef5_dir, regrid_to_solver)

        self.cfg = cfg
        self.log = cfg.progress or (lambda s: None)

        if cfg.dem_path:
            grid = SolverGrid.from_dem(cfg.dem_path, dtype=torch.float32,
                                       device="cpu")
        else:
            self.log(f"fetching 3DEP DEM (res {cfg.dem_res}) for {cfg.bbox}")
            z, tr, crs = demmod.load_dem(cfg.bbox, cfg.dem_res, cfg.dem_cache,
                                         cfg.max_cells)
            grid = SolverGrid.from_array(z, tr, crs, dtype=torch.float32,
                                         device="cpu")
        self.grid = grid
        ny, nx = grid.z.shape
        self.log(f"solver grid {ny}x{nx} ({ny * nx / 1e3:.0f}k cells, "
                 f"dx~{grid.dx:.0f} m)")
        self._write_dem = _write_dem

        # epoch: absolute datetime of sim t=0 for the WHOLE episode. Every
        # visit counts sim-seconds from here, so frame timestamps and the
        # 900 s output grid stay aligned across visits.
        self.epoch = cfg.sim_start or (cfg.t0 - datetime.timedelta(hours=6))

        # resume point: latest init_depth at or before t0 (junction state
        # published by a previous incarnation of this worker)
        t_state = self.epoch
        init_frame = None
        if resume:
            for p in glob.glob(os.path.join(cfg.ef5_output_dir,
                                            INIT_PREFIX + "*.tif")):
                try:
                    t_i = datetime.datetime.strptime(
                        os.path.basename(p)[len(INIT_PREFIX):-4], "%Y%m%d%H%M")
                except ValueError:
                    continue
                if self.epoch <= t_i <= cfg.t0 and \
                        (init_frame is None or t_i > init_frame[0]):
                    init_frame = (t_i, p)
            if init_frame:
                t_state = init_frame[0]

        # channel pre-wet from the q grid nearest the state time
        h0 = torch.zeros_like(grid.z)
        qs = parse_ef5_dir(cfg.ef5_output_dir, "q", cfg.model)
        if qs:
            import rasterio
            t_near, path = min(qs, key=lambda tp: abs(
                (tp[0] - t_state).total_seconds()))
            with rasterio.open(path) as ds:
                src = ds.read(1).astype(float)
                if ds.nodata is not None:
                    src = np.where(src == ds.nodata, 0.0, src)
                qg = regrid_to_solver(np.clip(src, 0, None), ds.transform,
                                      (ny, nx), grid.transform, ds.crs,
                                      grid.crs)
            h0, _, _ = initial_state_from_ef5(qg, None, grid.z, grid.dx,
                                              grid.dy)
            # pin to the grid's device: an ambient torch default device (e.g.
            # torch.set_default_device("cuda") in a host app) must not split
            # this CPU-side setup across devices
            qg_t = torch.as_tensor(qg).to(grid.z.device)
            h0 = torch.where(qg_t >= cfg.q_channel_min,
                             h0.to(torch.float32).to(grid.z.device),
                             torch.zeros_like(grid.z))
            self.log(f"channel pre-wet from q grid @ {t_near:%Y-%m-%d %H:%M} "
                     f"({int((qg >= cfg.q_channel_min).sum())} channel cells)")

        if init_frame:
            import rasterio
            t_i, p = init_frame
            with rasterio.open(p) as ds:
                prev = ds.read(1).astype(float) / 100.0        # uint16 cm -> m
                if ds.nodata is not None:
                    prev = np.where(prev == ds.nodata / 100.0, 0.0, prev)
                prev = regrid_to_solver(np.clip(prev, 0, None), ds.transform,
                                        (ny, nx), grid.transform, ds.crs,
                                        grid.crs)
            prev_t = torch.as_tensor(prev,
                                     dtype=torch.float32).to(grid.z.device)
            h0 = torch.maximum(h0, prev_t)
            self.log(f"session resumed at {t_i:%m-%d %H:%M} from "
                     f"{os.path.basename(p)} "
                     f"({int((prev_t > 0.02).sum())} wet cells; momentum at "
                     f"rest — skipping {(t_i - self.epoch).total_seconds() / 3600:.0f} h "
                     f"of anchored re-solve)")

        self.h = h0
        self.qx = torch.zeros_like(h0)
        self.qy = torch.zeros_like(h0)
        # obs-supported running max — survives tail rollbacks
        self.maxdepth = h0.clone()
        self.t = (t_state - self.epoch).total_seconds()
        self._nudged_once = False
        self.visit = None                 # active-visit dict, else parked

    # ------------------------------------------------------------------ #
    def state_time(self) -> datetime.datetime:
        return self.epoch + datetime.timedelta(seconds=round(self.t))

    # ------------------------------------------------------------------ #
    def begin_visit(self, forcing_dir: str, out_dir: str,
                    t0: datetime.datetime, t_end: datetime.datetime):
        """Open a visit for one bundle: integrate held state -> t_end, hold
        the state that will be KEPT at t0 (the bundle's obs junction)."""
        assert self.visit is None, "previous visit not ended"
        os.makedirs(out_dir, exist_ok=True)
        self._write_dem(os.path.join(out_dir, "dem.tif"), self.grid)
        t0_rel = (t0 - self.epoch).total_seconds()
        t_end_rel = (t_end - self.epoch).total_seconds()
        if t_end_rel <= self.t + 1e-6:
            raise ValueError(f"visit t_end {t_end} is not ahead of held "
                             f"state at {self.state_time()}")
        every = self.cfg.output_every_s
        self.visit = {
            "forcing_dir": forcing_dir, "out_dir": out_dir,
            "t0": t0, "t_end": t_end,
            "t0_rel": t0_rel, "t_end_rel": t_end_rel,
            "start_rel": self.t, "start": self.state_time(),
            "frames": [],
            # next frame on the episode-wide 900 s grid, strictly ahead
            "next_frame": (int(self.t // every) + 1) * every,
            "snapshot": None,
        }
        # re-emit the held state as this visit's first frame: publish
        # carry-forward keeps only frames strictly BEFORE sim_start, so
        # without this the junction frame would vanish on every catch-up
        # publish — and it is the frame restart recovery needs
        from . import io as iomod
        when = self.state_time()
        fname = f"depth_{when:%Y%m%d%H%M}.tif"
        iomod.write_depth(os.path.join(out_dir, fname),
                          self.h.detach().cpu().numpy(),
                          self.grid.transform, self.grid.crs)
        self.visit["frames"].append({"t": when.strftime("%Y-%m-%dT%H:%MZ"),
                                     "file": fname})
        # junction at/behind the held state (same-hour re-enqueue): the
        # whole visit is prediction tail — hold what we have right now
        if self.t >= t0_rel - 1e-6:
            self._take_snapshot()
        self.log(f"visit: {self.state_time():%m-%d %H:%M} -> "
                 f"{t_end:%m-%d %H:%M} (hold at {t0:%m-%d %H:%M}; "
                 f"{(t_end_rel - self.t) / 3600.0:.1f} sim-h)")

    def _take_snapshot(self):
        v = self.visit
        v["snapshot"] = (self.h.detach().cpu().clone(),
                         self.qx.detach().cpu().clone(),
                         self.qy.detach().cpu().clone(),
                         self.maxdepth.detach().cpu().clone(),
                         self.t)

    # ------------------------------------------------------------------ #
    def chunk(self, sim_s: float, device: str = "cuda") -> bool:
        """Integrate up to `sim_s` sim-seconds of the open visit on
        `device`; state returns to CPU before this call ends (ZeroGPU-safe).
        Returns True when the visit has reached t_end."""
        import torch
        from . import io as iomod
        from .forcing import EF5ChannelStage, ef5_forcing
        from .solver import SWESolver

        v = self.visit
        assert v is not None, "no open visit"
        cfg, grid = self.cfg, self.grid
        t_hi = min(self.t + float(sim_s), v["t_end_rel"])
        if v["snapshot"] is None:
            t_hi = min(t_hi, v["t0_rel"])     # land exactly on the junction

        z_d = grid.z.to(device)
        solver = SWESolver(z_d, dx=grid.dx, dy=grid.dy,
                           n_manning=cfg.n_manning, order=2, bc="open")
        rain = ef5_forcing(v["forcing_dir"], grid, self.epoch,
                           model=cfg.model, dtype=torch.float32,
                           device=device)
        try:
            nudge = EF5ChannelStage(v["forcing_dir"], grid, self.epoch,
                                    model=cfg.model, q_min=cfg.q_channel_min,
                                    dtype=torch.float32, device=device)
        except Exception as e:
            nudge = None
            if not self._nudged_once:
                self.log(f"channel coupling unavailable ({type(e).__name__})")

        h = self.h.to(device)
        qx = self.qx.to(device)
        qy = self.qy.to(device)
        md = self.maxdepth.to(device)
        if nudge is not None and not self._nudged_once:
            h = nudge(self.t, h)              # channel water present at start
            self._nudged_once = True

        state = {"md": md}

        def cb(t, h_, qx_, qy_):
            state["md"] = torch.maximum(state["md"], h_)
            if t + 1e-6 >= v["next_frame"] or t >= v["t_end_rel"] - 1e-6:
                when = self.epoch + datetime.timedelta(seconds=round(t))
                fname = f"depth_{when:%Y%m%d%H%M}.tif"
                iomod.write_depth(os.path.join(v["out_dir"], fname),
                                  h_.detach().cpu().numpy(),
                                  grid.transform, grid.crs)
                v["frames"].append({"t": when.strftime("%Y-%m-%dT%H:%MZ"),
                                    "file": fname})
                self.log(f"frame {fname} (sim t={t / 3600:.2f} h)")
                while v["next_frame"] <= t + 1e-6:
                    v["next_frame"] += cfg.output_every_s

        if t_hi > self.t + 1e-9:
            h, qx, qy = solver.run(h, qx, qy, t_end=t_hi, rain_fn=rain,
                                   t0=self.t, callback=cb, nudge_fn=nudge,
                                   dt_every=cfg.dt_every)
        self.h, self.qx, self.qy = h.cpu(), qx.cpu(), qy.cpu()
        self.maxdepth = state["md"].cpu()
        self.t = t_hi
        if v["snapshot"] is None and self.t >= v["t0_rel"] - 1e-6:
            self._take_snapshot()
        return self.t >= v["t_end_rel"] - 1e-9

    # ------------------------------------------------------------------ #
    def end_visit(self) -> dict:
        """Write maxdepth + this visit's manifest, then roll the held state
        back to the t0 snapshot (the prediction tail is published but NOT
        kept — the next visit re-does it with fresh observations)."""
        from . import io as iomod
        v = self.visit
        assert v is not None and self.t >= v["t_end_rel"] - 1e-9, \
            "visit not finished"
        cfg, grid = self.cfg, self.grid
        ny, nx = grid.z.shape
        iomod.write_depth(os.path.join(v["out_dir"], "maxdepth.tif"),
                          self.maxdepth.numpy(), grid.transform, grid.crs)
        manifest = {
            "event_id": cfg.event_id, "bbox": list(cfg.bbox),
            "t0": v["t0"].strftime("%Y-%m-%dT%H:%MZ"),
            "sim_start": v["start"].strftime("%Y-%m-%dT%H:%MZ"),
            "t_end": v["t_end"].strftime("%Y-%m-%dT%H:%MZ"),
            "model": cfg.model, "trigger": cfg.trigger,
            "grid": {"ny": ny, "nx": nx, "dx_m": round(grid.dx, 2),
                     "dy_m": round(grid.dy, 2),
                     "transform": list(grid.transform)[:6],
                     "crs": str(grid.crs) if grid.crs else None},
            "n_manning": cfg.n_manning, "frames": v["frames"],
            "maxdepth": "maxdepth.tif", "dem": "dem.tif",
            "generated": datetime.datetime.utcnow().strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        }
        with open(os.path.join(v["out_dir"], "manifest.json"), "w") as fp:
            json.dump(manifest, fp)
        # roll back to the junction: obs-supported state + maxdepth survive,
        # the tail (and its over/under-predictions) do not
        self.h, self.qx, self.qy, self.maxdepth, self.t = v["snapshot"]
        self.visit = None
        self.log(f"visit done — {len(manifest['frames'])} frames published; "
                 f"holding state at {self.state_time():%m-%d %H:%M} "
                 f"(momentum retained)")
        return manifest

    # ------------------------------------------------------------------ #
    def advance(self, forcing_dir: str, out_dir: str,
                t0: datetime.datetime, t_end: datetime.datetime,
                device: str = "cuda") -> dict:
        """One whole visit in-process (HPC path — no GPU-slice bound)."""
        self.begin_visit(forcing_dir, out_dir, t0, t_end)
        while not self.chunk(float("inf"), device=device):
            pass
        return self.end_visit()

    def park(self):
        """Explicitly drop any device references (state is already CPU
        after chunk(); kept for API symmetry with the brief)."""
        self.h = self.h.cpu()
        self.qx = self.qx.cpu()
        self.qy = self.qy.cpu()
        self.maxdepth = self.maxdepth.cpu()

    # ------------------------------------------------------------------ #
    # ZeroGPU fork plumbing: a @spaces.GPU child mutates a pickled COPY of
    # the session, so it must return the state for the parent to reapply.
    def state_tuple(self):
        v = self.visit
        return (self.h, self.qx, self.qy, self.maxdepth, self.t,
                self._nudged_once,
                (v["frames"], v["next_frame"], v["snapshot"]) if v else None)

    def set_state(self, tup):
        (self.h, self.qx, self.qy, self.maxdepth, self.t,
         self._nudged_once, vt) = tup
        if vt is not None and self.visit is not None:
            self.visit["frames"], self.visit["next_frame"], \
                self.visit["snapshot"] = vt
