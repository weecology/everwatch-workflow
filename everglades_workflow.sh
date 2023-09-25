#!/bin/bash
#SBATCH --job-name=everglades_workflow 
#SBATCH --mail-user=henrysenyondo@ufl.edu 
#SBATCH --mail-type=FAIL
#SBATCH --gpus=a100:4
#SBATCH --cpus-per-task=10
#SBATCH --mem=200gb
#SBATCH --time=8:00:00
#SBATCH --partition=gpu
#SBATCH --output=everglades_workflow.out
#SBATCH --error=everglades_workflow.err

echo "INFO: [$(date "+%Y-%m-%d %H:%M:%S")] Starting everglades workflow $(hostname) in $(pwd)"

conda activate EvergladesTools
srun snakemake --printshellcmds --keep-going --cores 10 --resources gpu=2 --rerun-incomplete
