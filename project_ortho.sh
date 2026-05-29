#!/usr/bin/env bash
# Reproject an orthomosaic to a target CRS.
#
# Drops the ODM alpha band first so the output is 3-band RGB,
# then warps to EPSG:<epsg> with nodata-filled borders. Extra gdalwarp
# options (e.g. -wo NUM_THREADS=N) are passed through via "$@".
#
# Usage: project_ortho.sh <input.tif> <output.tif> <epsg> [gdalwarp opts...]
set -euo pipefail

if [ "$#" -lt 3 ]; then
    echo "Usage: $0 <input.tif> <output.tif> <epsg> [gdalwarp opts...]" >&2
    exit 2
fi

input=$1
output=$2
epsg=$3
shift 3

vrt="${output}.rgb.vrt"
gdal_translate -of VRT -b 1 -b 2 -b 3 -a_nodata 255 "$input" "$vrt"
gdalwarp -overwrite -r bilinear -multi \
    -srcnodata 255 -dstnodata 255 \
    -wo INIT_DEST=NO_DATA -wo UNIFIED_SRC_NODATA=YES \
    -co TILED=YES -co COMPRESS=LZW -co PREDICTOR=2 -co BIGTIFF=YES \
    -co BLOCKXSIZE=512 -co BLOCKYSIZE=512 \
    -t_srs "EPSG:${epsg}" "$@" "$vrt" "$output"
rm -f "$vrt"
