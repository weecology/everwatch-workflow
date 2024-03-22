import os
import sys
from zipfile import ZIP_DEFLATED
from zipfile import ZipFile
import geopandas
import pandas as pd
import tools


def combine(paths):
    """Take prediction shapefiles and wrap into a single file"""
    shapefiles = []
    for x in paths:
        shapefiles.append(geopandas.read_file(x))
    summary = geopandas.GeoDataFrame(pd.concat(shapefiles, ignore_index=True), crs=shapefiles[0].crs)
    return summary


if __name__ == "__main__":
    working_dir = tools.get_working_dir()
    predictions_path = f"{working_dir}/predictions/"
    output_path = f"{working_dir}/EvergladesTools/App/Zooniverse/data"

    predictions = sys.argv[1:]
    # write output to zooniverse app
    df = combine(predictions)
    df.to_file(os.path.join(output_path, "PredictedBirds.shp"))

    # Zip the shapefile for storage efficiency
    with ZipFile(os.path.join(output_path, "PredictedBirds.zip"), 'w', ZIP_DEFLATED) as zip:
        for ext in ['cpg', 'dbf', 'prj', 'shp', 'shx']:
            focal_file = os.path.join(output_path, f"PredictedBirds.{ext}")
            file_name = os.path.basename(focal_file)
            zip.write(focal_file, arcname=file_name)
            os.remove(focal_file)
