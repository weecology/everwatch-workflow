#!/bin/bash
# Usage: bash create_ortho.sh <site> <year> <flight> <working_dir> <scratch_dir> [raw_dir]
#
# raw_dir is the folder holding this flight's images. The workflow passes it because
# each drone keeps its flights in its own folder under RawData; it is empty for
# flights that only exist as an archived orthomosaic.

set -euo pipefail

USAGE="Usage: $0 <site> <year> <flight> <working_dir> <scratch_dir> [raw_dir]"
SITE="${1:?$USAGE}"
YEAR="${2:?$USAGE}"
FLIGHT="${3:?$USAGE}"
WORKING_DIR="${4:?$USAGE}"
SCRATCH_DIR="${5:?$USAGE}"
SOURCE_FOLDER="${6:-}"
ODM_SIF="/blue/ewhite/everglades/open_drone_map/odm.sif"

ARCHIVE_PATH="${WORKING_DIR}/orthomosaics/${YEAR}/${SITE}/${FLIGHT}.tif"
OUTPUT_PATH="${WORKING_DIR}/orthomosaics_work/${YEAR}/${SITE}/${FLIGHT}.tif"

# Check if existing orthomosaic, and if so break early
mkdir -p "$(dirname "${OUTPUT_PATH}")"
if [[ -f "${ARCHIVE_PATH}" ]]; then
    ln -sfn "${ARCHIVE_PATH}" "${OUTPUT_PATH}"
    exit 0
fi

if [[ -z "${SOURCE_FOLDER}" ]]; then
    echo "No archived ortho (${ARCHIVE_PATH}) and no raw image folder was given for ${FLIGHT}" >&2
    exit 1
fi

if [[ ! -d "${SOURCE_FOLDER}" ]]; then
    echo "No archived ortho (${ARCHIVE_PATH}) and no raw data (${SOURCE_FOLDER})" >&2
    exit 1
fi

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
TARGET_DIR="${SCRATCH_DIR}/${FLIGHT}"
EXCLUDE_FILE="${SCRIPT_DIR}/exclude.txt"
IMAGE_LIST="${TARGET_DIR}/image_list.txt"

mkdir -p "${TARGET_DIR}/code"

python "${SCRIPT_DIR}/check_flight_gps.py" "${SOURCE_FOLDER}" \
    --exclude-file "${EXCLUDE_FILE}" --image-list "${IMAGE_LIST}" || {
    echo "Not enough geo-referenced images in ${SOURCE_FOLDER}; skipping ODM for ${FLIGHT}" >&2
    exit 1
}

source /blue/ewhite/everglades/open_drone_map/odm_env/bin/activate

printenv | grep -i slurm | sort


# Perform PPK geotagging
python "${SCRIPT_DIR}/wispr_to_odm_ppk.py" "${SOURCE_FOLDER}" "${TARGET_DIR}/code/geo.txt" || \
{ echo "Failed to find a PPK coordinate file. Processing will use EXIF GPS data only."; }

# Copy only geo-referenced images listed by check_flight_gps.py
echo "Copying $(wc -l < "${IMAGE_LIST}") images from ${SOURCE_FOLDER} to ${TARGET_DIR}/code/images"
mkdir -p "${TARGET_DIR}/code/images"
# Clear the folder first to avoid stale images from a previous failed run
rm -rf "${TARGET_DIR}/code/images"
rsync -av --files-from="${IMAGE_LIST}" "${SOURCE_FOLDER}/" "${TARGET_DIR}/code/images/" || \
{ echo "Failed to copy the images listed in ${IMAGE_LIST}"; exit 1; }

# Run GCP detection
mkdir -p "${TARGET_DIR}/gcp"
gcp-detect "${SOURCE_FOLDER}" --output "${TARGET_DIR}/gcp" gcps.csv && \
    cp "${TARGET_DIR}/gcp/gcp_list.txt" "${TARGET_DIR}/code/gcp_list.txt" || \
    echo "No GCPs found, proceeding without."

# Unload the environment to avoid conflicts inside the container. It seems
# the host env can pollute the environment and cause errors late into 
# processing that are actually unrelated to the imagery. Note this is not
# a conda environment, it's a venv from the `source` earlier in the script.
deactivate
module load cuda

# Run ODM with the target directory as project path.
# ODM records how the run ended in log.json inside the project folder.
ODM_LOG_JSON="${TARGET_DIR}/code/log.json"
echo "Running ODM on ${TARGET_DIR}"
if ! apptainer run --nv --bind "${TARGET_DIR}:/project" \
    "$ODM_SIF" \
    --project-path /project \
    --max-concurrency 4 \
    --orthophoto-resolution 1 \
    --optimize-disk-space \
    --rerun-all \
    --build-overviews \
    --split 400 \
    --skip-3dmodel \
    --split-overlap 100 \
    --cog; then

    # Some ODM failures are about the images themselves, so a rerun would fail the
    # same way; exclude those flights. Everything else (out of memory, job timeout,
    # node problems) is left alone so the workflow can retry it.
    if [[ -f "${ODM_LOG_JSON}" ]] && grep -Eq \
        "Not enough supported images|Not enough images in selected band|could not process this dataset using the current settings" \
        "${ODM_LOG_JSON}"; then
        python "${SCRIPT_DIR}/exclude_flight.py" "${SOURCE_FOLDER}" \
            --exclude-file "${EXCLUDE_FILE}" \
            --reason "${FLIGHT}: ODM could not build an orthomosaic from these images"
    fi
    echo "ODM failed for ${FLIGHT}; see this rule's log" >&2
    exit 1
fi

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
