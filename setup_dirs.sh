#!/bin/bash
# Create and permission all working directories needed by the Snakemake pipeline.
# Usage: bash setup_dirs.sh <working_dir>
set -euo pipefail

WORKING_DIR="${1:?Usage: $0 <working_dir>}"

dirs=(
    orthomosaics
    projected_mosaics
    projected_mosaics/webmercator
    predictions
    detected_nests
    processed_nests
    mapbox
    mapbox/last_uploaded
    logs
    everwatch-workflow/App/Zooniverse/data
)

echo "INFO: Setting up directories under ${WORKING_DIR}"
failed=()
for d in "${dirs[@]}"; do
    full="${WORKING_DIR}/${d}"
    mkdir -p "${full}"
    chmod g+ws "${full}" 2>/dev/null || true
    if [[ ! -w "${full}" ]]; then
        failed+=("${full}")
    fi
done

if [[ ${#failed[@]} -gt 0 ]]; then
    echo "ERROR: The following directories exist but are not writable." >&2
    echo "       Ask the directory owner to run: chmod g+w <dir>" >&2
    for f in "${failed[@]}"; do
        echo "       ${f}  (owner: $(stat -c '%U' "${f}" 2>/dev/null || stat -f '%Su' "${f}"))" >&2
    done
    exit 1
fi
echo "INFO: Done"
