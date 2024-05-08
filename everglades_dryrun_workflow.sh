#!/bin/bash
#SBATCH --job-name=everwatch_workflow_dryrun
#SBATCH --mail-user=henrysenyondo@ufl.edu
#SBATCH --mail-type=FAIL
#SBATCH --gpus=a100:1
#SBATCH --cpus-per-task=3
#SBATCH --mem=200gb
#SBATCH --time=01:30:00
#SBATCH --partition=gpu
#SBATCH --output=/blue/ewhite/everglades/everwatch-workflow/logs/everglades_dryrun_workflow.out
#SBATCH --error=/blue/ewhite/everglades/everwatch-workflow/logs/everglades_dryrun_workflow.err

echo "INFO: [$(date "+%Y-%m-%d %H:%M:%S")] Starting everglades workflow on $(hostname) in $(pwd)"

echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Loading required modules"
source /etc/profile.d/modules.sh

ml conda
conda activate everwatch
export TEST_ENV=True

cd /blue/ewhite/everglades/everwatch-workflow/

snakemake --unlock
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Starting Snakemake pipeline"
snakemake --printshellcmds --keep-going --cores 3 --resources gpu=1 --rerun-incomplete --latency-wait 1 --use-conda
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] End"
