#!/bin/bash
#SBATCH --job-name=everglades_workflow 
#SBATCH --mail-user=henrysenyondo@ufl.edu 
#SBATCH --mail-type=FAIL
#SBATCH --gpus=a100:4
#SBATCH --cpus-per-task=5
#SBATCH --mem=1000gb
#SBATCH --time=180:00:00
#SBATCH --partition=gpu
#SBATCH --output=/blue/ewhite/everglades/EvergladesTools/logs/everglades_dryrun_workflow.out
#SBATCH --error=/blue/ewhite/everglades/EvergladesTools/logs/everglades_dryrun_workflow.err

echo "INFO: [$(date "+%Y-%m-%d %H:%M:%S")] Starting everglades workflow on $(hostname) in $(pwd)"

echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Loading required modules"
source /etc/profile.d/modules.sh

ml conda
# conda env create --force --file /blue/ewhite/everglades/EvergladesTools/Zooniverse/environment.yml

conda activate EvergladesTools
export TEST_ENV=True

cd /blue/ewhite/everglades/EvergladesTools/Zooniverse
snakemake --unlock
snakemake --printshellcmds --keep-going --cores 5 --resources gpu=4 --rerun-incomplete --latency-wait 10 --use-conda
