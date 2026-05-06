#!/bin/bash
# Run from a tmux session on the login node:  bash everglades_dryrun_workflow.sh

source /blue/ewhite/hpc_maintenance/githubdeploytoken.txt

echo "INFO: [$(date "+%Y-%m-%d %H:%M:%S")] Starting everglades workflow on $(hostname) in $(pwd)"

source /etc/profile.d/modules.sh
ml conda
conda activate everwatch
export PYTHONNOUSERSITE=1

export TEST_ENV=True
# Guardrails for memory-heavy raster jobs
export GDAL_CACHEMAX=4096
export RASTERIO_MAX_DATASET_CACHE=64
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

cd /blue/ewhite/everglades/everwatch-workflow/

snakemake --unlock
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Starting Snakemake pipeline"
snakemake \
  --executor slurm \
  --printshellcmds \
  --keep-going \
  --use-conda \
  --rerun-incomplete \
  --latency-wait 60 \
  --jobs 20

echo ""
echo "=============================="
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] End"
