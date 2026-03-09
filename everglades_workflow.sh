#!/bin/bash
#SBATCH --job-name=everglades_workflow 
#SBATCH --mail-user=henrysenyondo@ufl.edu 
#SBATCH --mail-type=FAIL
#SBATCH --cpus-per-task=20
#SBATCH --mem=160gb
#SBATCH --gpus=1
#SBATCH --time=80:00:00
#SBATCH --output=/blue/ewhite/everglades/everwatch-workflow/logs/everglades_workflow.out
#SBATCH --error=/blue/ewhite/everglades/everwatch-workflow/logs/everglades_workflow.err

source /blue/ewhite/hpc_maintenance/githubdeploytoken.txt

echo "INFO: [$(date "+%Y-%m-%d %H:%M:%S")] Starting everglades workflow on $(hostname) in $(pwd)"

echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Loading required modules"
source /etc/profile.d/modules.sh

ml conda
conda activate everwatch
export PYTHONNOUSERSITE=1
cd /blue/ewhite/everglades/everwatch-workflow/

snakemake --unlock
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Starting Snakemake pipeline"
snakemake \
  --printshellcmds \
  --keep-going \
  --use-conda \
  --rerun-incomplete \
  --latency-wait 10 \
  --cores 20 \
  --jobs 2 \
  --resources mem_mb=160000 gpu=1 project_mosaic_slot=1 predict_birds_slot=1

echo ""
echo "=============================="
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] End"
