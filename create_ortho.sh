#!/bin/bash
# Usage: bash create_ortho.sh <site> <year> <flight> <working_dir> <scratch_dir>

set -euo pipefail

SITE="${1:?Usage: $0 <site> <year> <flight> <working_dir> <scratch_dir>}"
YEAR="${2:?Usage: $0 <site> <year> <flight> <working_dir> <scratch_dir>}"
FLIGHT="${3:?Usage: $0 <site> <year> <flight> <working_dir> <scratch_dir>}"
WORKING_DIR="${4:?Usage: $0 <site> <year> <flight> <working_dir> <scratch_dir>}"
SCRATCH_DIR="${5:?Usage: $0 <site> <year> <flight> <working_dir> <scratch_dir>}"
ODM_SIF="/blue/ewhite/everglades/open_drone_map/odm.sif"

SOURCE_FOLDER="${WORKING_DIR}/open_drone_map/RawData/SkyScoutFlights/${SITE}/${FLIGHT}"
ARCHIVE_PATH="${WORKING_DIR}/orthomosaics/${YEAR}/${SITE}/${FLIGHT}.tif"
OUTPUT_PATH="${WORKING_DIR}/orthomosaics_work/${YEAR}/${SITE}/${FLIGHT}.tif"

# Check if existing orthomosaic, and if so break early
mkdir -p "$(dirname "${OUTPUT_PATH}")"
if [[ -f "${ARCHIVE_PATH}" ]]; then
    ln -sfn "${ARCHIVE_PATH}" "${OUTPUT_PATH}"
    exit 0
fi

if [[ ! -d "${SOURCE_FOLDER}" ]]; then
    echo "No archived ortho (${ARCHIVE_PATH}) and no raw data (${SOURCE_FOLDER})" >&2
    exit 1
fi

source /blue/ewhite/everglades/open_drone_map/odm_env/bin/activate

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
TARGET_DIR="${SCRATCH_DIR}/${FLIGHT}"

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
apptainer run --nv --bind "${TARGET_DIR}:/project" \
    "$ODM_SIF" \
    --project-path /project \
    --max-concurrency 8 \
    --orthophoto-resolution 1 \
    --optimize-disk-space \
    --rerun-all \
    --build-overviews \
    --cog

# Clean up images
echo "Removing image folder ${TARGET_DIR}/code/images"
rm -rf "${TARGET_DIR}/code/images"

# Copy orthomosaic to the requested output path
ODM_OUTPUT="${TARGET_DIR}/code/odm_orthophoto/odm_orthophoto.tif"
echo "Copying ${ODM_OUTPUT} to ${ARCHIVE_PATH}"
mkdir -p "$(dirname "${ARCHIVE_PATH}")"
cp "${ODM_OUTPUT}" "${ARCHIVE_PATH}"
ln -sfn "${ARCHIVE_PATH}" "${OUTPUT_PATH}"

echo "Setting permissions on target folder"
bash /home/veitchmichaelisj/bin/group-permissions-update.sh "${TARGET_DIR}"

echo "Completed processing ${FLIGHT}"
