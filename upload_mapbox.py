import os
import requests
import sys
import subprocess
import tomli
import tools

import rasterio as rio
from rasterio.warp import calculate_default_transform, reproject, Resampling


def on_mapbox(flight):
    """Check if the mbtiles file has already been uploaded to mapbox"""
    with open("/blue/ewhite/everglades/mapbox/mapbox.ini", "rb") as f:
        toml_dict = tomli.load(f)
        token = toml_dict['mapbox']['access-token']
    api_base_url = "https://api.mapbox.com/v4"
    tileset_id = f"bweinstein.{flight}"
    url = f"{api_base_url}/{tileset_id}.json?access_token={token}"
    response = requests.get(url)
    return response.status_code == 200


def upload(path, year, site, force_upload=False):
    # Create output filename
    basename = os.path.splitext(os.path.basename(path))[0]
    flight = basename.replace("_projected", "")
    if tools.get_event(basename) == "Primary":
        # If from the primary flight strip any extra metadata from filename
        flight = "_".join(basename.split('_')[0:4])
    mbtiles_dir = os.path.join("/blue/ewhite/everglades/mapbox/", year, site)
    if not os.path.exists(mbtiles_dir):
        os.makedirs(mbtiles_dir)
    mbtiles_filename = os.path.join(mbtiles_dir, f"{flight}.mbtiles")

    # Generate tiles
    print("Creating mbtiles file")
    subprocess.run([
        "rio", "mbtiles", path, "-o", mbtiles_filename, "--zoom-levels", "17..24", "-j", "4", "-f", "PNG",
        "--progress-bar"
    ])

    # Upload to mapbox
    print("Uploading to mapbox")
    if force_upload or not on_mapbox(flight):
        subprocess.run(["mapbox", "upload", f"bweinstein.{basename}", mbtiles_filename])
    else:
        print(f"{flight} is already on Mapbox, not uploading. To force reupload use --force-upload")

    return mbtiles_filename


if __name__ == "__main__":
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[6]
    site = split_path[7]
    if len(sys.argv) == 3 and sys.argv[2] == "--force-upload":
        force_upload = True
    else:
        force_upload = False
    upload(path, year, site, force_upload=force_upload)
