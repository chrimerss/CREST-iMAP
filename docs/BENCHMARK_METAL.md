# Apple Metal benchmark

**Machine:** Apple M4 Max (12 performance + 4 efficiency cores), 64 GB, PyTorch 2.15.0.
**Case:** `benchmarks/metal/bench_devices.py`: 50 mm/h rain on a partly flooded rough
bed, 30 m cells, float32, second order, adaptive `SWESolver.step`. MCUPS is million
cell-steps per second.

**This is not a clean CPU comparison.** A virtual machine was holding about 13 cores
and the load average stayed between 150 and 320, so the 12-thread CPU run was badly
oversubscribed: at 1024² one thread beat twelve (2.82 vs 1.09 steps/s). Those
12-thread numbers are left out. Instead, the CPU limit below is the best single-thread
rate per CPU-second times 16, which assumes perfect scaling on all 16 cores. Real
scaling is lower, while load may also have held the single-thread rate down, so treat
it as an estimate. The GPU ran under the same load and may also be understated.

| Grid | Metal steps/s | Metal MCUPS | CPU MCUPS per core | CPU limit (16 cores) | Metal vs limit |
|---|---|---|---|---|---|
| 64² | 54 | 0.2 | not measured | | |
| 128² | 115 | 1.9 | not measured | | |
| 256² | 166 | 10.8 | 4.2 | 67 | not shown faster |
| 512² | 157 | 41.3 | 3.7 | 59 | not shown faster |
| 1024² | 64 | 67.3 | 3.0 | 48 | at least 1.4× |
| 2048² | 15.6 | 65.4 | 2.7 | 43 | at least 1.5× |
| 4096² | 3.5 | 59.3 | not measured | | |

- **Grid size:** Metal levels off at 60–67 MCUPS from about 1024². Small grids are
  poor: the 64² rate is 0.2 MCUPS. `device="auto"` still picks Metal there, so pass
  `device="cpu"` for small grids.
- **Against CUDA:** the Harvey run in [`BENCHMARK_HARVEY.md`](BENCHMARK_HARVEY.md) took
  53.2 ms per step on 11.2 M cells on an A100, about 210 MCUPS, so this GPU is roughly
  3× slower. That compares different terrain, forcing and solver versions, so it is
  only a rough guide.
- **Accuracy:** over 1800 sim-seconds on 256², Metal and CPU float32 both differ from
  CPU float64 by about 9.4e-6 m RMSE (4.3e-5 and 4.5e-5 m at worst), and both lose
  1.7e-6 of the water, where float64 shows no measurable loss.
- **Gradients:** 20 steps forward and backward on 512² took 0.42 s on Metal. That bed
  has dry cells, which give NaN gradients on every device, so this measures time only.
  On a fully wet domain, Metal and CPU gradients agree (`tests/test_metal.py`).

**Not measured:** energy (`powermetrics` needs root), the Harvey case (its data is not
on this machine), and `dt_every` or dry-start retries on Metal.

For a clean baseline, stop other heavy work and rerun:

```bash
python benchmarks/metal/bench_devices.py --sizes 256 512 1024 2048 4096 --out metal.json
```
