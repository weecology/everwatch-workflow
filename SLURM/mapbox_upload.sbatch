#!/bin/bash
#SBATCH --job-name=mapbox_upload   # Job name
#SBATCH --mail-type=END               # Mail events
#SBATCH --mail-user=benweinstein2010@gmail.com  # Where to send mail
#SBATCH --account=ewhite
#SBATCH --nodes=1                 # Number of MPI ranks
#SBATCH --cpus-per-task=1
#SBATCH --mem=70GB
#SBATCH --time=72:00:00       #Time limit hrs:min:sec
#SBATCH --output=/home/b.weinstein/logs/mapbox_upload.out   # Standard output and error log
#SBATCH --error=/home/b.weinstein/logs/mapbox_upload.err

conda activate DeepTreeAttention

cd /home/b.weinstein/everwatch-workflow
python upload_mapbox.py
