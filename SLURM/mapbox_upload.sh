sbatch <<EOT
#!/bin/bash
#SBATCH --job-name=mapbox_upload   # Job name
#SBATCH --mail-type=END               # Mail events
#SBATCH --mail-user=ethanwhite@ufl.edu  # Where to send mail
#SBATCH --account=ewhite
#SBATCH --nodes=1                 # Number of MPI ranks
#SBATCH --cpus-per-task=1
#SBATCH --mem=50GB
#SBATCH --time=72:00:00       #Time limit hrs:min:sec
#SBATCH --output=/blue/ewhite/everglades/EvergladesTools/Zooniverse/logs/mapbox_upload.out   # Standard output and error log
#SBATCH --error=/blue/ewhite/everglades/EvergladesTools/Zooniverse/logs/mapbox_upload.err

source activate EvergladesTools

cd /blue/ewhite/everglades/EvergladesTools/Zooniverse
python upload_mapbox.py
EOT