#!/bin/bash
#SBATCH --job-name=everglades_workflow 
#SBATCH --mail-user=henrysenyondo@ufl.edu 
#SBATCH --mail-type=FAIL
#SBATCH --gpus=a100:4
#SBATCH --cpus-per-task=10
#SBATCH --mem=200gb
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
snakemake --printshellcmds --keep-going --cores 10 --resources gpu=4 --rerun-incomplete --latency-wait 10 --use-conda
