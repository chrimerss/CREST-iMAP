#!/bin/bash
# V27 P1 GPU event worker — nohup wrapper in the style of
# nowcast_space/run_train.sh (survives SSH disconnect, logs to worker.log).
#
#   ./run_worker.sh                    # shadow validation (default: --no-publish)
#   ./run_worker.sh --publish          # ONLY after EVENT_QUEUE_MODE=on
#   ./run_worker.sh --once --no-publish  # single-job validation run
#
# Extra args pass through to `python -m crestimap.worker`.
cd "$(dirname "$0")"

export HF_TOKEN=$(tr -d ' \r\n' < ~/huggingface.txt)
export SCRATCH=${SCRATCH:-/media/scratch/$USER}
export HF_HOME=${HF_HOME:-$SCRATCH/hf_cache}
export EVENT_DEM_CACHE=${EVENT_DEM_CACHE:-$SCRATCH/dem_cache}   # 10 m tiles ~400 MB each
export CREST_AI_DIR=${CREST_AI_DIR:-$SCRATCH/crest_worker/CREST_AI}
export WORKER_WORK_ROOT=${WORKER_WORK_ROOT:-$SCRATCH/crest_worker/jobs}
# Cell budget for THIS card (never coarsen — oversized jobs are left to the
# ladder). RTX 4500 Ada 24 GB: ~50 M cells leaves solver headroom; raise on
# an 80 GB A100 to the brief's 100 M default.
export EVENT_MAX_CELLS_GPU=${EVENT_MAX_CELLS_GPU:-50000000}
# CFL recompute cadence: hold 0.9x dt between recomputes to avoid the
# per-step device->host sync (validated: gates 1-4 pass at 10).
export EVENT_DT_EVERY=${EVENT_DT_EVERY:-10}

nohup python -u -m crestimap.worker "$@" > worker.log 2>&1 &
echo "worker started, PID $!  —  watch with:  tail -f worker.log"
