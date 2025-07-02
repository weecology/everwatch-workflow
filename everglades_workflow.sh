#!/bin/bash
#SBATCH --job-name=everglades_workflow 
#SBATCH --mail-user=henrysenyondo@ufl.edu 
#SBATCH --mail-type=FAIL
#SBATCH --cpus-per-task=30
#SBATCH --mem=250gb
#SBATCH --gpus=5
#SBATCH --time=100:00:00
#SBATCH --partition=hpg-b200
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
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Starting Snakemake pipeline"
snakemake --printshellcmds --keep-going --cores 30 --resources gpu=5 --rerun-incomplete --latency-wait 10 --software-deployment-method conda
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] End"
