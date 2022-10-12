import glob
import os
import re
from zipfile import ZIP_DEFLATED
from zipfile import ZipFile

import geopandas
import pandas as pd


def find_shp_files(nests_path):
    files = glob.glob(os.path.join(nests_path, '**', '**', '*_processed_nests.shp'))
    return files


def get_site(path):
    path = os.path.basename(path)
    regex = re.compile("(\\w+)_\\d+.*_processed_nests")
    return regex.match(path).group(1)


def load_shapefile(x):
    print(x)
    shp = geopandas.read_file(x)
    shp["site"] = get_site(x)
    return shp


def combine(paths):
    """Take prediction shapefiles and wrap into a single file"""
    shapefiles = []
    for x in paths:
        try:
            shapefiles.append(load_shapefile(x))
        except:
            print(f"Mistructured file path: {x}. File not added to processed_nests.shp")
    summary = geopandas.GeoDataFrame(pd.concat(shapefiles, ignore_index=True), crs=shapefiles[0].crs)

    return summary


if __name__ == "__main__":
    nests_path = "/blue/ewhite/everglades/processed_nests/"
    output_path = "/blue/ewhite/everglades/EvergladesTools/App/Zooniverse/data/"

    nest_files = find_shp_files(nests_path)
    # write output to zooniverse app
    df = combine(nest_files)
    df.to_file(os.path.join(output_path, "nest_detections_processed.shp"))

    # Zip the shapefile for storage efficiency
    with ZipFile("../App/Zooniverse/data/nest_detections_processed.zip", 'w', ZIP_DEFLATED) as zip:
        for ext in ['cpg', 'dbf', 'prj', 'shp', 'shx']:
            focal_file = os.path.join(output_path, f"nest_detections_processed.{ext}")
            file_name = os.path.basename(focal_file)
            zip.write(focal_file, arcname=file_name)
            os.remove(focal_file)
