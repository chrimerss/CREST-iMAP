"""V27 P1: single-GPU event worker daemon (HPC side of hf_data/eventqueue.py).

Polls `events/queue/` on the CREST_data dataset for job specs the Space
enqueues (docs/P1_WORKER_BRIEF.md is the executable contract), claims one
job at a time, downloads its EF5 forcing bundle, runs the FULL-BASIN
native-resolution solve on the GPU via `crestimap.run_event`, and hands the
results to CREST_AI's own rendering/publishing code (`hf_data.eventsim` /
`hf_data.eventstore`) — nothing is reimplemented on this side.

Queue protocol (mirrors hf_data/eventqueue.py exactly):

  events/queue/<id>.json             job spec (written by the Space)
  events/queue/<id>.forcing.tar.gz   EF5 output grids for the window
  events/queue/<id>.claim            {"worker": "<host>:<pid>", "hb": ISO}
  events/queue/<id>.failed.json      worker error report; job consumed

A claim is stale (re-claimable) when its heartbeat is older than
--stale-s (600 s, the Space's EVENT_CLAIM_FRESH_S); we re-commit ours
every --hb-s (240 s). Hourly episode re-simulations REPLACE the spec under
the same id — we always record the spec's `queued` stamp at claim time and
leave a replaced spec alone at cleanup.

Publishing is OFF by default (`--no-publish`): results stay in the local
job dir for validation while the Space runs in shadow mode and solves the
same event itself. Pass `--publish` ONLY after the user flips the Space to
EVENT_QUEUE_MODE=on; only then does the worker publish via
eventstore.publish_event and consume queue entries.

Never prints or logs the HF token.
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import shutil
import socket
import sys
import tarfile
import tempfile
import threading
import time
import traceback

TS = "%Y-%m-%dT%H:%M:%SZ"
TMIN = "%Y-%m-%dT%H:%MZ"
DEM_RES_DEG = {"1": 1.0 / 3600.0, "13": 1.0 / 10800.0}
QPREFIX = "events/queue"


def _utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _log(msg: str):
    print(f"[{_utcnow():%Y-%m-%d %H:%M:%S}Z] {msg}", flush=True)


def _load_token() -> str:
    tok = os.environ.get("HF_TOKEN", "").strip()
    if not tok:
        with open(os.path.expanduser("~/huggingface.txt")) as fp:
            tok = fp.read().strip()
        os.environ["HF_TOKEN"] = tok      # eventsim/eventstore read it from env
    return tok


def expected_cells(spec: dict) -> int:
    """Native-resolution cell count of the FULL-BASIN domain — the pre-claim
    capacity check. This is what keeps `dem.load_dem`'s silent block-mean
    path (resolution coarsening) from ever engaging: an oversized job is
    simply never claimed and falls through the ladder to the CPU window."""
    w, s, e, n = spec["bbox_basin"]
    res = DEM_RES_DEG.get(str(spec.get("dem_res", "1")), DEM_RES_DEG["1"])
    return int(round((n - s) / res)) * int(round((e - w) / res))


class Worker:
    def __init__(self, args):
        from huggingface_hub import HfApi
        self.args = args
        self.repo = args.repo
        self.token = _load_token()
        self.api = HfApi(token=self.token)
        self.ident = f"{socket.gethostname()}:{os.getpid()}"
        # V30 provenance: publish_event stamps the manifest with this
        os.environ.setdefault("EVENT_ENGINE_IDENT", f"hpc:{self.ident}")
        self.max_cells = args.max_cells
        self.publish = args.publish
        # (event_id, queued) pairs already processed this session. With
        # --no-publish the queue entry is never consumed (the Space owns it),
        # so without this the same spec would be re-claimed every poll. An
        # episode re-sim REPLACES the spec with a new `queued` stamp, so
        # replacements still run. In-memory only: a restart re-runs at most
        # the latest episode of each queued event, which shadow mode can eat.
        self.done = set()
        # P1.6: ev_id -> {"session": EventSession, "root": episode workdir,
        # "bbox": spec bbox, "visits": int, "last": wall time}. RAM-only —
        # a restart recovers via the bundle's init_depth (hierarchy level 2).
        self.sessions = {}
        self._hb_stop = None
        sys.path.insert(0, os.path.abspath(args.crest_ai))
        os.makedirs(args.work_root, exist_ok=True)
        os.environ.setdefault(
            "EVENT_DEM_CACHE",
            os.path.join("/media/scratch", os.environ.get("USER", "worker"),
                         "dem_cache"))

    # ---------------------------------------------------------------- #
    # queue plumbing
    # ---------------------------------------------------------------- #
    def _dl(self, path: str, force=True) -> str | None:
        from huggingface_hub import hf_hub_download
        try:
            return hf_hub_download(self.repo, path, repo_type="dataset",
                                   token=self.token, force_download=force)
        except Exception:
            return None

    def _read_json(self, path: str) -> dict | None:
        p = self._dl(path)
        if p is None:
            return None
        try:
            with open(p, encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            return None

    def _claim_fresh(self, claim: dict | None) -> bool:
        if not claim:
            return False
        try:
            hb = datetime.datetime.strptime(claim.get("hb", ""), TS)
        except ValueError:
            return False
        return (_utcnow() - hb).total_seconds() < self.args.stale_s

    def _commit(self, ops, message: str) -> bool:
        try:
            self.api.create_commit(repo_id=self.repo, repo_type="dataset",
                                   operations=ops, commit_message=message)
            return True
        except Exception as e:
            _log(f"commit failed ({message}): {type(e).__name__}: {e}")
            return False

    def _commit_claim(self, ev: str, queued: str) -> bool:
        from huggingface_hub import CommitOperationAdd
        body = json.dumps({"worker": self.ident,
                           "hb": _utcnow().strftime(TS),
                           "queued": queued})
        return self._commit(
            [CommitOperationAdd(f"{QPREFIX}/{ev}.claim",
                                io.BytesIO(body.encode()))],
            f"claim {ev} [{self.ident}]")

    def scan_candidates(self) -> list[dict]:
        """ALL claimable job specs, oldest queued first. Applies the
        capacity check BEFORE claiming (never coarsen — standing
        directive)."""
        try:
            files = self.api.list_repo_files(self.repo, repo_type="dataset")
        except Exception as e:
            _log(f"list_repo_files failed: {type(e).__name__}: {e}")
            return []
        qf = [f for f in files if f.startswith(QPREFIX + "/")]
        ids = sorted({os.path.basename(f)[:-5] for f in qf
                      if f.endswith(".json")
                      and not f.endswith(".failed.json")})
        cands = []
        for ev in ids:
            if f"{QPREFIX}/{ev}.forcing.tar.gz" not in qf:
                continue                       # spec without bundle: not ready
            spec = self._read_json(f"{QPREFIX}/{ev}.json")
            if not spec:
                continue
            if (ev, spec.get("queued", "")) in self.done:
                continue                       # this episode already ran
            cells = expected_cells(spec)
            if cells > self.max_cells:
                _log(f"skip {ev}: {cells / 1e6:.1f} M cells at native "
                     f"res exceeds the {self.max_cells / 1e6:.0f} M budget "
                     f"(falls through to the CPU window; never coarsened)")
                continue
            if f"{QPREFIX}/{ev}.claim" in qf:
                claim = self._read_json(f"{QPREFIX}/{ev}.claim")
                if self._claim_fresh(claim) and \
                        claim.get("worker") != self.ident:
                    continue                   # someone else is on it
            cands.append((spec.get("queued", ""), ev, spec))
        cands.sort()
        return [{"id": ev, "spec": spec} for _, ev, spec in cands]

    def scan(self) -> dict | None:
        cands = self.scan_candidates()
        return cands[0] if cands else None

    def claim(self, job: dict) -> bool:
        ev, queued = job["id"], job["spec"].get("queued", "")
        if not self._commit_claim(ev, queued):
            return False
        time.sleep(3)                          # settle, then verify we won
        claim = self._read_json(f"{QPREFIX}/{ev}.claim")
        if not claim or claim.get("worker") != self.ident:
            _log(f"lost claim race on {ev} to "
                 f"{(claim or {}).get('worker', '?')}")
            return False
        return True

    def _start_heartbeat(self, ev: str, queued: str):
        stop = threading.Event()

        def beat():
            while not stop.wait(self.args.hb_s):
                self._commit_claim(ev, queued)
        th = threading.Thread(target=beat, daemon=True,
                              name=f"hb-{ev}")
        th.start()
        self._hb_stop = stop
        return stop

    # ---------------------------------------------------------------- #
    # job execution
    # ---------------------------------------------------------------- #
    def process(self, job: dict) -> bool:
        from crestimap import EventConfig, run_event
        from hf_data import eventsim, eventstore   # CREST_AI reuse — no rewrite

        ev = job["id"]
        spec = job["spec"]
        queued = spec.get("queued", "")
        workdir = tempfile.mkdtemp(prefix=f"job_{ev}_",
                                   dir=self.args.work_root)
        forcing_dir = os.path.join(workdir, "forcing")
        out_dir = os.path.join(workdir, "out")
        os.makedirs(forcing_dir, exist_ok=True)
        hb = self._start_heartbeat(ev, queued)
        t_wall = time.time()
        try:
            tar = self._dl(f"{QPREFIX}/{ev}.forcing.tar.gz")
            if tar is None:
                raise FileNotFoundError(f"{ev}.forcing.tar.gz gone from queue")
            with tarfile.open(tar) as tf:
                tf.extractall(forcing_dir)
            _log(f"{ev}: forcing bundle extracted "
                 f"({len(os.listdir(forcing_dir))} grids)")

            cfg = EventConfig(
                event_id=ev, bbox=tuple(spec["bbox_basin"]),
                t0=datetime.datetime.strptime(spec["t0"], TMIN),
                t_end=datetime.datetime.strptime(spec["t_end"], TMIN),
                sim_start=datetime.datetime.strptime(spec["sim_start"], TMIN),
                ef5_output_dir=forcing_dir, out_dir=out_dir,
                model=spec.get("model", "crest"),
                dem_res=str(spec.get("dem_res", "1")),
                dem_cache=os.environ["EVENT_DEM_CACHE"],
                max_cells=self.max_cells,
                trigger=spec.get("trigger"), device=self.args.device,
                dt_every=self.args.dt_every,
                progress=lambda s: _log(f"{ev}: {s}"))
            manifest = run_event(cfg)

            # exactly the tail of eventsim.run_one
            manifest["gauge"] = spec["gauge"]["id"]
            manifest["hydro"] = spec.get("hydro") or []
            manifest["status"] = "active"
            manifest["basin"] = spec.get("basin")
            eventsim._update_archive(cfg.out_dir, manifest,
                                     lambda s: _log(f"{ev}: {s}"))
            if not manifest.get("archive_frames"):
                manifest["status"] = "ended"
                manifest["dry"] = True
            eventsim._make_pngs(cfg.out_dir, manifest)
            _log(f"{ev}: rendered {len(manifest['frames'])} PNG overlays; "
                 f"solve+render wall-clock {time.time() - t_wall:.0f} s")

            if self.publish:
                ok = eventstore.publish_event(cfg.out_dir, manifest)
                _log(f"{ev}: publish {'OK' if ok else 'FAILED'}")
                if not ok:
                    raise RuntimeError("publish_event returned False")
            else:
                _log(f"{ev}: --no-publish — results kept in {cfg.out_dir}")
            self._cleanup_queue(ev, queued, success=True)
            self.done.add((ev, queued))
            shutil.rmtree(forcing_dir, ignore_errors=True)
            return True
        except Exception as e:
            tb_tail = "\n".join(
                traceback.format_exc().strip().splitlines()[-8:])
            _log(f"{ev}: FAILED — {type(e).__name__}: {e}\n{tb_tail}")
            self._report_failure(ev, queued, e, tb_tail)
            self.done.add((ev, queued))        # don't retry a poison episode
            return False
        finally:
            hb.set()

    def _spec_unchanged(self, ev: str, queued: str) -> bool:
        cur = self._read_json(f"{QPREFIX}/{ev}.json")
        if cur is None:
            return False                       # spec gone (swept/consumed)
        if cur.get("queued", "") != queued:
            _log(f"{ev}: spec was replaced mid-run (episode re-sim) — "
                 f"leaving the new bundle for the next poll")
            return False
        return True

    def _cleanup_queue(self, ev: str, queued: str, success: bool):
        from huggingface_hub import CommitOperationDelete
        ops = [CommitOperationDelete(f"{QPREFIX}/{ev}.claim")]
        if self.publish and success and self._spec_unchanged(ev, queued):
            ops += [CommitOperationDelete(f"{QPREFIX}/{ev}.json"),
                    CommitOperationDelete(f"{QPREFIX}/{ev}.forcing.tar.gz")]
        self._commit(ops, f"worker done {ev} "
                          f"({'consumed' if len(ops) > 1 else 'claim only'})")

    def _report_failure(self, ev: str, queued: str, exc, tb_tail: str):
        """Publishing enabled: consume the job with a failed.json so the
        queue never wedges on a poison job. Shadow phase: only release the
        claim — the Space solved the event itself and owns the entry."""
        from huggingface_hub import (CommitOperationAdd,
                                     CommitOperationDelete)
        ops = [CommitOperationDelete(f"{QPREFIX}/{ev}.claim")]
        if self.publish and self._spec_unchanged(ev, queued):
            body = json.dumps({
                "worker": self.ident,
                "failed": _utcnow().strftime(TS),
                "error": f"{type(exc).__name__}: {exc}"[:2000],
                "traceback_tail": tb_tail[:4000]})
            ops += [CommitOperationAdd(f"{QPREFIX}/{ev}.failed.json",
                                       io.BytesIO(body.encode())),
                    CommitOperationDelete(f"{QPREFIX}/{ev}.json"),
                    CommitOperationDelete(f"{QPREFIX}/{ev}.forcing.tar.gz")]
        self._commit(ops, f"worker failed {ev}")

    # ---------------------------------------------------------------- #
    # P1.6 resident sessions + cooperative scheduling (--sessions)
    # ---------------------------------------------------------------- #
    def process_visit(self, job: dict) -> bool:
        """One bundle -> one session visit. Known episode: catch up from the
        held junction state (minutes). New episode: cold/resumed anchored
        solve, then the session stays resident for the next bundle."""
        from crestimap import EventConfig
        from crestimap.session import EventSession
        from hf_data import eventsim, eventstore   # CREST_AI reuse

        ev = job["id"]
        spec = job["spec"]
        queued = spec.get("queued", "")
        rec = self.sessions.get(ev)
        if rec and rec["bbox"] != spec["bbox_basin"]:
            _log(f"{ev}: bbox changed — dropping resident session")
            shutil.rmtree(rec["root"], ignore_errors=True)
            self.sessions.pop(ev, None)
            rec = None

        if rec is None:
            root = tempfile.mkdtemp(prefix=f"sess_{ev}_",
                                    dir=self.args.work_root)
            rec = {"session": None, "root": root,
                   "bbox": spec["bbox_basin"], "visits": 0,
                   "last": time.time()}
        n = rec["visits"] + 1
        forcing_dir = os.path.join(rec["root"], f"forcing_{n}")
        out_dir = os.path.join(rec["root"], f"out_{n}")
        os.makedirs(forcing_dir, exist_ok=True)
        hb = self._start_heartbeat(ev, queued)
        t_wall = time.time()
        try:
            tar = self._dl(f"{QPREFIX}/{ev}.forcing.tar.gz")
            if tar is None:
                raise FileNotFoundError(f"{ev}.forcing.tar.gz gone from queue")
            with tarfile.open(tar) as tf:
                tf.extractall(forcing_dir)
            t0 = datetime.datetime.strptime(spec["t0"], TMIN)
            t_end = datetime.datetime.strptime(spec["t_end"], TMIN)

            if rec["session"] is None:
                cfg = EventConfig(
                    event_id=ev, bbox=tuple(spec["bbox_basin"]),
                    t0=t0, t_end=t_end,
                    sim_start=datetime.datetime.strptime(spec["sim_start"],
                                                         TMIN),
                    ef5_output_dir=forcing_dir, out_dir=out_dir,
                    model=spec.get("model", "crest"),
                    dem_res=str(spec.get("dem_res", "1")),
                    dem_cache=os.environ["EVENT_DEM_CACHE"],
                    max_cells=self.max_cells,
                    trigger=spec.get("trigger"), device=self.args.device,
                    dt_every=self.args.dt_every,
                    progress=lambda s: _log(f"{ev}: {s}"))
                rec["session"] = EventSession(cfg, resume=True)
            manifest = rec["session"].advance(forcing_dir, out_dir, t0, t_end,
                                              device=self.args.device)

            # exactly the tail of eventsim.run_one
            manifest["gauge"] = spec["gauge"]["id"]
            manifest["hydro"] = spec.get("hydro") or []
            manifest["status"] = "active"
            manifest["basin"] = spec.get("basin")
            eventsim._update_archive(out_dir, manifest,
                                     lambda s: _log(f"{ev}: {s}"))
            if not manifest.get("archive_frames"):
                manifest["status"] = "ended"
                manifest["dry"] = True
            eventsim._make_pngs(out_dir, manifest)
            _log(f"{ev}: visit {n} — {len(manifest['frames'])} frames, "
                 f"wall {time.time() - t_wall:.0f} s")

            if self.publish:
                ok = eventstore.publish_event(out_dir, manifest)
                _log(f"{ev}: publish {'OK' if ok else 'FAILED'}")
                if not ok:
                    raise RuntimeError("publish_event returned False")
            else:
                _log(f"{ev}: --no-publish — results kept in {out_dir}")
            self._cleanup_queue(ev, queued, success=True)
            self.done.add((ev, queued))
            rec["visits"] = n
            rec["last"] = time.time()
            self.sessions[ev] = rec
            # bound disk: only the just-published visit's dirs remain
            for stale in os.listdir(rec["root"]):
                if stale not in (f"forcing_{n}", f"out_{n}"):
                    shutil.rmtree(os.path.join(rec["root"], stale),
                                  ignore_errors=True)
            return True
        except Exception as e:
            tb_tail = "\n".join(
                traceback.format_exc().strip().splitlines()[-8:])
            _log(f"{ev}: visit FAILED — {type(e).__name__}: {e}\n{tb_tail}")
            self._report_failure(ev, queued, e, tb_tail)
            self.done.add((ev, queued))        # don't retry a poison episode
            # mid-visit state is not trustworthy — drop; the next bundle
            # rebuilds via init_depth
            if ev in self.sessions:
                shutil.rmtree(self.sessions[ev]["root"], ignore_errors=True)
                del self.sessions[ev]
            elif rec is not None:
                shutil.rmtree(rec["root"], ignore_errors=True)
            return False
        finally:
            hb.set()

    def _evict_sessions(self):
        """Drop sessions for ended episodes (events/index.json), for
        episodes idle past --evict-idle-h, and LRU beyond --max-sessions."""
        if not self.sessions:
            return
        # events/index.json is flat {event_id: summary} (eventstore.load_index)
        idx = self._read_json("events/index.json") or {}
        ended = {eid for eid, meta in idx.items()
                 if isinstance(meta, dict) and meta.get("status") == "ended"}
        now = time.time()
        for ev in list(self.sessions):
            idle_h = (now - self.sessions[ev]["last"]) / 3600.0
            if ev in ended or idle_h > self.args.evict_idle_h:
                why = "episode ended" if ev in ended else \
                    f"idle {idle_h:.0f} h"
                _log(f"evicting session {ev} ({why})")
                shutil.rmtree(self.sessions[ev]["root"], ignore_errors=True)
                del self.sessions[ev]
        while len(self.sessions) > self.args.max_sessions:
            ev = min(self.sessions, key=lambda e: self.sessions[e]["last"])
            _log(f"evicting session {ev} (LRU, cap "
                 f"{self.args.max_sessions})")
            shutil.rmtree(self.sessions[ev]["root"], ignore_errors=True)
            del self.sessions[ev]

    def run_sessions(self):
        """P1.6 scheduler: bundles for resident sessions first (a catch-up
        visit is minutes), then new events; claims are held only while a
        visit is actively advancing — while every session waits for forcing
        this worker is free for B, C, D, ..."""
        _log(f"worker {self.ident} up (P1.6 sessions): repo={self.repo} "
             f"device={self.args.device} "
             f"max_cells={self.max_cells / 1e6:.0f}M "
             f"max_sessions={self.args.max_sessions} "
             f"publish={'ON' if self.publish else 'OFF (shadow validation)'}")
        while True:
            try:
                cands = self.scan_candidates()
                known = [j for j in cands if j["id"] in self.sessions]
                new = [j for j in cands if j["id"] not in self.sessions]
                for job in known + new:
                    ev = job["id"]
                    kind = "catch-up" if ev in self.sessions else "new"
                    _log(f"claiming {ev} ({kind}, "
                         f"{expected_cells(job['spec']) / 1e6:.1f} M cells)")
                    if self.claim(job):
                        self.process_visit(job)
                        break                  # re-scan: freshest queue view
                self._evict_sessions()
                if self.args.once:
                    return
            except Exception as e:
                _log(f"session loop error: {type(e).__name__}: {e}")
            time.sleep(self.args.poll_s)

    # ---------------------------------------------------------------- #
    def run_forever(self):
        _log(f"worker {self.ident} up: repo={self.repo} "
             f"device={self.args.device} max_cells={self.max_cells / 1e6:.0f}M "
             f"publish={'ON' if self.publish else 'OFF (shadow validation)'}")
        while True:
            try:
                job = self.scan()
                if job is not None:
                    ev = job["id"]
                    _log(f"claiming {ev} "
                         f"({expected_cells(job['spec']) / 1e6:.1f} M cells)")
                    if self.claim(job):
                        self.process(job)
                        if self.args.once:
                            return
            except Exception as e:
                _log(f"poll loop error: {type(e).__name__}: {e}")
            if self.args.once and job is None:
                _log("--once and no claimable job — exiting")
                return
            time.sleep(self.args.poll_s)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=os.environ.get("CREST_DATA_REPO",
                                                     "vincewin/CREST_data"))
    ap.add_argument("--crest-ai", default=os.environ.get(
        "CREST_AI_DIR", os.path.expanduser("~/CREST_AI")),
        help="path to the CREST_AI clone (hf_data reuse; never pushed)")
    ap.add_argument("--work-root", default=os.environ.get(
        "WORKER_WORK_ROOT",
        os.path.join("/media/scratch", os.environ.get("USER", "worker"),
                     "crest_worker", "jobs")))
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--max-cells", type=int,
                    default=int(os.environ.get("EVENT_MAX_CELLS_GPU",
                                               "100000000")))
    ap.add_argument("--poll-s", type=int, default=60)
    ap.add_argument("--hb-s", type=int, default=240)
    ap.add_argument("--stale-s", type=int, default=600)
    ap.add_argument("--dt-every", type=int,
                    default=int(os.environ.get("EVENT_DT_EVERY", "1")),
                    help="recompute the CFL dt every k steps (held value "
                         "carries a 0.9 safety factor); 1 = every step")
    ap.add_argument("--once", action="store_true",
                    help="process at most one job, then exit (validation)")
    ap.add_argument("--sessions", action="store_true",
                    default=os.environ.get("EVENT_SESSIONS", "") == "1",
                    help="P1.6 resident-session scheduler: hold per-event "
                         "solver state (incl. momentum) between bundles and "
                         "interleave events while episodes wait for forcing. "
                         "OFF by default until docs/P1_6_VALIDATION.md is GO.")
    ap.add_argument("--max-sessions", type=int,
                    default=int(os.environ.get("EVENT_MAX_SESSIONS", "6")),
                    help="LRU cap on resident sessions (~75 MB RAM each at "
                         "4.7 M cells)")
    ap.add_argument("--evict-idle-h", type=float,
                    default=float(os.environ.get("EVENT_EVICT_IDLE_H", "12")),
                    help="drop a session when its episode has sent no new "
                         "bundle for this many hours")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--publish", dest="publish", action="store_true",
                   help="publish results + consume queue entries — ONLY "
                        "after the Space is flipped to EVENT_QUEUE_MODE=on")
    g.add_argument("--no-publish", dest="publish", action="store_false",
                   help="shadow validation (default): keep results local")
    ap.set_defaults(publish=False)
    args = ap.parse_args(argv)
    w = Worker(args)
    if args.sessions:
        w.run_sessions()
    else:
        w.run_forever()


if __name__ == "__main__":
    main()
