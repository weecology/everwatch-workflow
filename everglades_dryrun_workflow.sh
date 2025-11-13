#!/bin/bash
#SBATCH --job-name=everwatch_workflow_dryrun
#SBATCH --mail-user=henrysenyondo@ufl.edu
#SBATCH --mail-type=FAIL
#SBATCH --cpus-per-task=6
#SBATCH --mem=90gb
#SBATCH --time=09:30:00
#SBATCH --gpus=1
#SBATCH --output=/blue/ewhite/everglades/everwatch-workflow/logs/everglades_dryrun_workflow.out
#SBATCH --error=/blue/ewhite/everglades/everwatch-workflow/logs/everglades_dryrun_workflow.err

source /blue/ewhite/hpc_maintenance/githubdeploytoken.txt

echo "INFO: [$(date "+%Y-%m-%d %H:%M:%S")] Starting everglades workflow on $(hostname) in $(pwd)"

echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Loading required modules"
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
  --printshellcmds \
  --keep-going \
  --use-conda \
  --rerun-incomplete \
  --latency-wait 10 \
  --cores 3 \
  --resources mem_mb=90000 gpu=1

echo ""
echo "=============================="
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] End"
