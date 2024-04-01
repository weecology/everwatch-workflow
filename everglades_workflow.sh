#!/bin/bash
#SBATCH --job-name=everglades_workflow 
#SBATCH --mail-user=henrysenyondo@ufl.edu 
#SBATCH --mail-type=FAIL
#SBATCH --gpus=a100:1
#SBATCH --cpus-per-task=30
#SBATCH --mem=1200gb
#SBATCH --time=80:00:00
#SBATCH --partition=gpu
#SBATCH --output=/blue/ewhite/everglades/EvergladesTools/logs/everglades_workflow.out
#SBATCH --error=/blue/ewhite/everglades/EvergladesTools/logs/everglades_workflow.err

echo "INFO: [$(date "+%Y-%m-%d %H:%M:%S")] Starting everglades workflow on $(hostname) in $(pwd)"

echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Loading required modules"
source /etc/profile.d/modules.sh

ml conda
conda activate EvergladesTools

cd /blue/ewhite/everglades/EvergladesTools/Zooniverse

snakemake --unlock
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Starting Snakemake pipeline"
snakemake --printshellcmds --keep-going --cores 30 --resources gpu=1 --rerun-incomplete --latency-wait 10 --use-conda
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] End"
