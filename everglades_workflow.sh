#!/bin/bash
#SBATCH --job-name=everglades_workflow 
#SBATCH --mail-user=henrysenyondo@ufl.edu 
#SBATCH --mail-type=FAIL
#SBATCH --cpus-per-task=1
#SBATCH --mem=4gb
#SBATCH --time=15:00:00
#SBATCH --output=/blue/ewhite/everglades/everwatch-workflow/logs/everglades_workflow.out
#SBATCH --error=/blue/ewhite/everglades/everwatch-workflow/logs/everglades_workflow.err

source /blue/ewhite/hpc_maintenance/githubdeploytoken.txt

echo "INFO: [$(date "+%Y-%m-%d %H:%M:%S")] Starting everglades workflow on $(hostname) in $(pwd)"

echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Loading required modules"
source /etc/profile.d/modules.sh

ml conda
conda activate everwatch

cd /blue/ewhite/everglades/everwatch-workflow/

snakemake --unlock

echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Starting Snakemake pipeline in cluster mode"
snakemake --printshellcmds --keep-going --jobs 5 --latency-wait 10 --use-conda --default-resources cpus=6 mem_mb=46000 --slurm-partition hpg-default --slurm-time 15:00:00 --slurm-output logs/snakejob_%j.out --slurm-error logs/snakejob_%j.err

echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] End"
