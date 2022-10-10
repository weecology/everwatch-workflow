sbatch <<EOT
#!/bin/bash
#SBATCH --job-name=NestDetect   # Job name
#SBATCH --mail-type=END,FAIL            # Mail events
#SBATCH --mail-user=ethanwhite@ufl.edu  # Where to send mail
#SBATCH --account=ewhite
#SBATCH --nodes=1                 # Number of MPI ran
#SBATCH --cpus-per-task=8
#SBATCH --mem=62GB
#SBATCH --time=72:00:00       #Time limit hrs:min:sec
#SBATCH --output=/blue/ewhite/everglades/EvergladesTools/Zooniverse/logs/nest_detector_%j.out   # Standard output and error log
#SBATCH --error=/blue/ewhite/everglades/EvergladesTools/Zooniverse/logs/nest_detector_%j.err
#SBATCH --partition=hpg-default
ulimit -c 0
cd /blue/ewhite/everglades/EvergladesTools/Zooniverse
source activate EvergladesTools
python nest_detection.py
EOT
