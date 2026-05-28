#!/bin/bash
# Run from a tmux session on the login node:  bash everglades_workflow.sh

source /blue/ewhite/hpc_maintenance/githubdeploytoken.txt

echo "INFO: [$(date "+%Y-%m-%d %H:%M:%S")] Starting everglades workflow on $(hostname) in $(pwd)"

source /etc/profile.d/modules.sh
ml conda
conda activate everwatch
export PYTHONNOUSERSITE=1
export TEST_ENV = 1
cd /blue/ewhite/everglades/everwatch-workflow/

bash setup_dirs.sh /blue/ewhite/everglades

snakemake --unlock
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] Starting Snakemake pipeline"
snakemake --profile profiles/slurm

echo ""
echo "=============================="
echo "INFO [$(date "+%Y-%m-%d %H:%M:%S")] End"
