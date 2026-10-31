"""CREST-iMAP v2 solver throughput: CPU vs Apple Metal (mps).

Synthetic rain on a partly flooded rough bed, on the production path: float32,
second order, adaptive `SWESolver.step`. Each device and grid size runs in its own
process so peak memory is that run's alone. No data is needed:

    python benchmarks/metal/bench_devices.py --sizes 256 512 1024 2048 \
        --out metal.json

Other load on the machine moves the CPU numbers far more than the GPU ones, so the
load average is recorded with every result. Check it before quoting a ratio.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import resource
import statistics
import subprocess
import sys
import time

import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from crestimap.solver import SWESolver                   # noqa: E402

DX = 30.0
RAIN_M_S = 50.0 / 1000.0 / 3600.0   # 50 mm/h
POOL_M = 15.0


def bed(n):
    """Same terrain at every size and on every device, built in float64 on CPU."""
    s = torch.linspace(0.0, 1.0, n, dtype=torch.float64)
    y, x = torch.meshgrid(s, s, indexing="ij")
    tau = 2.0 * torch.pi
    z = (40.0 * x + 10.0 * torch.sin(tau * 3 * x) * torch.sin(tau * 2 * y)
         + 5.0 * torch.sin(tau * 9 * y) * torch.cos(tau * 7 * x))
    return z.clamp(min=0.0)


def setup(n, device, dtype):
    z = bed(n).to(dtype=dtype, device=device)
    h = (POOL_M - z).clamp(min=0.0)
    q = torch.zeros_like(z)
    rain = torch.full_like(z, RAIN_M_S)
    return SWESolver(z, DX, DX, n_manning=0.05), h, q, q.clone(), rain


def wait(device):
    if device == "mps":
        torch.mps.synchronize()


def throughput(n, device, budget_s, repeats):
    """Steps per second, after warm-up steps that are not counted. Each repeat
    starts from the same state, and the same number of steps on every device."""
    solver, h0, qx0, qy0, rain = setup(n, device, torch.float32)
    h, qx, qy = h0, qx0, qy0
    t = time.perf_counter()
    for _ in range(3):
        h, qx, qy, _ = solver.step(h, qx, qy, rain=rain)
    wait(device)
    first = (time.perf_counter() - t) / 3.0
    steps = max(10, min(2000, int(budget_s / max(first, 1e-4))))
    rates, cpu_rates = [], []
    for _ in range(repeats):
        h, qx, qy = h0, qx0, qy0
        for _ in range(3):
            h, qx, qy, _ = solver.step(h, qx, qy, rain=rain)
        wait(device)
        t, c = time.perf_counter(), time.process_time()
        for _ in range(steps):
            h, qx, qy, _ = solver.step(h, qx, qy, rain=rain)
        h.sum().item()
        wait(device)
        rates.append(steps / (time.perf_counter() - t))
        cpu_rates.append(steps / (time.process_time() - c))
    # per CPU-second, on one thread, is the figure that survives a loaded machine
    out = {"steps": steps, "rates": rates, "retries": solver.n_retries,
           "threads": torch.get_num_threads(),
           "best_mcups_per_cpu_s": max(cpu_rates) * n * n / 1e6,
           "steps_per_s": statistics.median(rates),
           "mcups": statistics.median(rates) * n * n / 1e6,
           "peak_rss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30}
    if device == "mps":
        out["gpu_alloc_gib"] = torch.mps.driver_allocated_memory() / 2**30
    return out


def gradient(n, device, nsteps=20):
    """Seconds for one forward + backward through nsteps, w.r.t. Manning n."""
    solver, h, qx, qy, rain = setup(n, device, torch.float32)
    solver.n = torch.as_tensor(0.05, dtype=h.dtype, device=h.device).requires_grad_()
    t = time.perf_counter()
    for _ in range(nsteps):
        h, qx, qy, _ = solver.step(h, qx, qy, dt=0.5, rain=rain)
    h.sum().backward()
    g = solver.n.grad.item()
    wait(device)
    return {"nsteps": nsteps, "seconds": time.perf_counter() - t, "grad": g}


def fidelity(n, device, dtype, t_end):
    """Integrate t_end sim-seconds; return depths plus cost and mass balance."""
    solver, h, qx, qy, rain = setup(n, device, dtype)
    start = h.cpu().double().sum().item()
    t, nsteps, wall = 0.0, 0, time.perf_counter()
    while t < t_end:
        h, qx, qy, dt = solver.step(h, qx, qy, rain=rain)
        t += dt
        nsteps += 1
    h = h.detach().cpu().double()
    supplied = start + RAIN_M_S * t * n * n
    return h, {"t": t, "steps": nsteps, "retries": solver.n_retries,
               "seconds": time.perf_counter() - wall,
               "mass_error": h.sum().item() / supplied - 1.0}


def compare(n, t_end):
    runs = {"cpu_f64": ("cpu", torch.float64), "cpu_f32": ("cpu", torch.float32),
            "mps_f32": ("mps", torch.float32)}
    depth, out = {}, {}
    for name, (device, dtype) in runs.items():
        depth[name], out[name] = fidelity(n, device, dtype, t_end)
    ref = depth["cpu_f64"]
    for name, h in depth.items():
        d = h - ref
        out[name]["rmse_vs_f64_m"] = d.pow(2).mean().sqrt().item()
        out[name]["max_diff_vs_f64_m"] = d.abs().max().item()
    return out


def child(args):
    if args.threads:
        torch.set_num_threads(args.threads)
    if args.mode == "throughput":
        r = throughput(args.n, args.device, args.budget, args.repeats)
    elif args.mode == "gradient":
        r = gradient(args.n, args.device)
    else:
        r = compare(args.n, args.t_end)
    r.update(mode=args.mode, n=args.n, device=args.device, load=os.getloadavg()[0])
    print(json.dumps(r), flush=True)


def spawn(args, mode, n, device):
    cmd = [sys.executable, __file__, "--child", "--mode", mode, "--n", str(n),
           "--device", device, "--budget", str(args.budget),
           "--repeats", str(args.repeats), "--t-end", str(args.t_end),
           "--threads", str(args.threads)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"mode": mode, "n": n, "device": device, "error": r.stderr[-400:]}
    return json.loads(r.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizes", type=int, nargs="+", default=[256, 512, 1024, 2048])
    ap.add_argument("--devices", nargs="+", default=["cpu", "mps"])
    ap.add_argument("--budget", type=float, default=30.0,
                    help="target seconds per repeat")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--t-end", type=float, default=1800.0,
                    help="sim-seconds for the accuracy comparison")
    ap.add_argument("--fidelity-n", type=int, default=256)
    ap.add_argument("--threads", type=int, default=0,
                    help="CPU threads (0 = torch default)")
    ap.add_argument("--throughput-only", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--child", action="store_true")
    ap.add_argument("--mode", default="throughput")
    ap.add_argument("--n", type=int, default=256)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()
    if args.child:
        return child(args)

    results = []
    for n in args.sizes:
        for device in args.devices:
            r = spawn(args, "throughput", n, device)
            results.append(r)
            print(r if "error" in r else
                  f"{n:5d}^2 {device:4s} {r['steps_per_s']:9.2f} steps/s "
                  f"{r['mcups']:8.1f} MCUPS rss {r['peak_rss_gib']:5.2f} GiB "
                  f"load {r['load']:.0f} "
                  f"best/cpu-s {r['best_mcups_per_cpu_s']:.1f}", flush=True)
    if args.throughput_only:
        args.out and pathlib.Path(args.out).write_text(json.dumps(results, indent=1))
        return
    for device in args.devices:
        r = spawn(args, "gradient", min(512, max(args.sizes)), device)
        results.append(r)
        print(r if "error" in r else
              f"gradient {r['n']}^2 {device:4s} {r['seconds']:.2f} s", flush=True)
    r = spawn(args, "fidelity", args.fidelity_n, "mps")
    results.append(r)
    print(json.dumps(r, indent=1), flush=True)
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
