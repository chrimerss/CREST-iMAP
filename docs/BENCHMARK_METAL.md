# Apple Metal and A100 benchmark

**Machine:** Apple M4 Max (12 performance + 4 efficiency cores), 64 GB, PyTorch 2.15.0.
**Case:** `benchmarks/metal/bench_devices.py`: 50 mm/h rain on a partly flooded rough
bed, 30 m cells, float32, second order, adaptive `SWESolver.step`. MCUPS is million
cell-steps per second. Load average was 4–11 during the runs, with nothing else heavy
running, and repeats agreed within about 4%.

| Grid | Metal steps/s | Metal MCUPS | CPU 12 threads MCUPS | CPU 1 thread MCUPS | Metal vs best CPU |
|---|---|---|---|---|---|
| 64² | 240 | 1.0 | 1.7 | 2.5 | 0.4× |
| 128² | 231 | 3.8 | 3.0 | 3.8 | 1.0× |
| 256² | 268 | 17.6 | 2.0 | 4.5 | 3.9× |
| 512² | 214 | 56.0 | 5.6 | 4.0 | 10× |
| 1024² | 74 | 77.9 | 5.7 | 3.4 | 14× |
| 2048² | 14.6 | 61.1 | 9.6 | 3.0 | 6.3× |
| 4096² | 3.2 | 54.3 | 9.5 | not measured | 5.7× |

- **Grid size:** Metal is fastest around 1024² and worth using from about 256² up. At
  64² CPU is faster, and at 128² they tie. `device="auto"` still picks Metal on those
  small grids, so pass `device="cpu"` there.
- **CPU threads:** twelve threads never beat one by more than about 3×, and up to 256²
  they are slower than one. For small grids on CPU, try `torch.set_num_threads(1)`.
- **Whole runs:** 1800 sim-seconds on 256² (1620 steps) took 6.3 s on Metal and 56 s on
  CPU with 12 threads.
- **Memory:** at 4096² Metal had 5.0 GiB allocated at the end of the run (peak not
  measured), and the CPU run peaked at 4.8 GiB.
- **Against CUDA:** the same case on an A100 is below. The A100 is 2.8–3.2× faster
  from 2048² up, but the Mac is faster up to 512².
- **Accuracy:** in that 256² run, Metal and CPU float32 both differ from CPU float64 by
  about 9.4e-6 m RMSE (4.3e-5 and 4.5e-5 m at worst), and both lose 1.7e-6 of the
  water, where float64 shows no measurable loss.
- **Gradients:** 20 steps forward and backward on 512² took 0.37 s on Metal and 3.2 s
  on CPU with 12 threads, one cold call each, so Metal's first-run setup is included.
  This measures time only; `tests/test_metal.py` checks that Metal and CPU gradients
  agree.

**Not measured:** energy (`powermetrics` needs root), the Harvey case (its data is not
on this machine), and `dt_every` or dry-start retries on Metal. This case had no
retries.

To reproduce, with nothing else heavy running:

```bash
python benchmarks/metal/bench_devices.py --sizes 64 128 256 512 1024 2048 4096 --budget 15 --out metal.json
```

```bash
python benchmarks/metal/bench_devices.py --sizes 64 128 256 512 1024 2048 --devices cpu --threads 1 --budget 15 --throughput-only --out cpu_1thread.json
```

## NVIDIA A100

**Machine:** one A100-SXM4-40GB on Stanford Sherlock (`serc` partition, driver
550.163.01), with 8 cores of an AMD EPYC 7662 at 2.0 GHz. The node was shared with
other jobs, at load 25–49 on 128 cores. PyTorch 2.10.0 with CUDA 12.8 (Sherlock's
`py-pytorch/2.10.0_py314` module), against 2.15.0 on the Mac. Same case and script as
above.

| Grid | A100 steps/s | A100 MCUPS | A100 peak GiB | Metal MCUPS | A100 vs Metal |
|---|---|---|---|---|---|
| 64² | 100 | 0.4 | 0.00 | 1.0 | 0.4× |
| 128² | 101 | 1.7 | 0.00 | 3.8 | 0.4× |
| 256² | 98.5 | 6.5 | 0.02 | 17.6 | 0.4× |
| 512² | 100 | 26.3 | 0.07 | 56.0 | 0.5× |
| 1024² | 99 | 104 | 0.26 | 77.9 | 1.3× |
| 2048² | 41.2 | 173 | 1.04 | 61.1 | 2.8× |
| 4096² | 10.4 | 174 | 4.14 | 54.3 | 3.2× |
| 8192² | 2.7 | 179 | 16.6 | not measured | |

- **Up to 1024² the A100 runs about 100 steps/s at every size**, so each step costs a
  fixed ~10 ms whatever the grid. That looks like launch overhead:
  [`BENCHMARK_HARVEY.md`](BENCHMARK_HARVEY.md) counts ~2000 unfused array passes per
  step. The Mac pays about 4 ms a step there, so small grids run faster on it.
- **From 2048² up the GPU is the limit**, at 173–179 MCUPS. The Harvey run on an A100,
  with an older solver, got about 210 MCUPS on 11.2 M cells.
- **Whole runs:** 1800 sim-seconds on 256² took 16.3 s on the A100 and 6.3 s on Metal.
- **Accuracy:** A100 float32 differs from CPU float64 by 9.3e-6 m RMSE (4.6e-5 m at
  worst) and loses 1.7e-6 of the water, the same as Metal and CPU float32.
- **Gradients:** 20 steps forward and backward on 512² took 0.99 s, one cold call, as
  on Metal.
- **Tests:** every test file passes on this GPU with `CRESTIMAP_TEST_DEVICE=cuda`, with
  `test_event` and `test_session` run on their own as on Metal. Those two, all on small
  grids, took 804 s here and 293 s on Metal.

```bash
python benchmarks/metal/bench_devices.py --sizes 64 128 256 512 1024 2048 4096 8192 --devices cuda --budget 15 --out a100.json
```
