#!/bin/bash
# Usage: bash process_ortho.sh <source_folder> <output_tif> <working_dir>
#   source_folder  - directory containing raw JPG images
#   output_tif     - destination path for the final orthomosaic .tif
#   working_dir    - scratch directory for ODM intermediate files

set -euo pipefail

SOURCE_FOLDER="${1:?Usage: $0 <source_folder> <output_tif> <working_dir>}"
OUTPUT_PATH="${2:?Usage: $0 <source_folder> <output_tif> <working_dir>}"
WORKING_DIR="${3:?Usage: $0 <source_folder> <output_tif> <working_dir>}"
ODM_SIF="/blue/ewhite/everglades/open_drone_map/odm.sif"

source /blue/ewhite/everglades/open_drone_map/odm_env/bin/activate

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
BASENAME=$(basename "$SOURCE_FOLDER")
TARGET_DIR="${WORKING_DIR}/${BASENAME}"

printenv | grep -i slurm | sort

mkdir -p "${TARGET_DIR}/code"

# Perform PPK geotagging
python "${SCRIPT_DIR}/wispr_to_odm_ppk.py" "${SOURCE_FOLDER}" "${TARGET_DIR}/code/geo.txt" || \
{ echo "Failed to find a PPK coordinate file. Processing will use EXIF GPS data only."; }

# Copy JPG files
echo "Copying images from ${SOURCE_FOLDER} to ${TARGET_DIR}/code/images"
mkdir -p "${TARGET_DIR}/code/images"
rsync -av --include='*.JPG' --include='*.jpg' --exclude='*' "${SOURCE_FOLDER}/" "${TARGET_DIR}/code/images/" || \
{ echo "Warning: No JPG files found in ${SOURCE_FOLDER}"; exit 1; }

# Run GCP detection
mkdir -p "${TARGET_DIR}/gcp"
gcp-detect "${SOURCE_FOLDER}" --output "${TARGET_DIR}/gcp" gcps.csv && \
    cp "${TARGET_DIR}/gcp/gcp_list.txt" "${TARGET_DIR}/code/gcp_list.txt" || \
    echo "No GCPs found, proceeding without."

module load cuda

# Run ODM with the target directory as project path
echo "Running ODM on ${TARGET_DIR}"
srun apptainer run --nv --bind "${TARGET_DIR}:/project" \
    "$ODM_SIF" \
    --project-path /project \
    --max-concurrency 8 \
    --orthophoto-resolution 2 \
    --optimize-disk-space \
    --build-overviews \
    --cog

# Clean up images
echo "Removing image folder ${TARGET_DIR}/code/images"
rm -rf "${TARGET_DIR}/code/images"

# Copy orthomosaic to the requested output path
ODM_OUTPUT="${TARGET_DIR}/code/odm_orthophoto/odm_orthophoto.tif"
echo "Copying ${ODM_OUTPUT} to ${OUTPUT_PATH}"
mkdir -p "$(dirname "${OUTPUT_PATH}")"
cp "${ODM_OUTPUT}" "${OUTPUT_PATH}"

echo "Setting permissions on target folder"
bash /home/veitchmichaelisj/bin/group-permissions-update.sh "${TARGET_DIR}"

echo "Completed processing ${BASENAME}"
