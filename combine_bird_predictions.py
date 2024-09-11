import os
import sys
import shutil
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
    output_path = f"{working_dir}/everwatch-workflow/App/Zooniverse/data"
    output_zip = os.path.join(output_path, "PredictedBirds.zip")

    predictions = sys.argv[1:]
    # write output to zooniverse app
    df = combine(predictions)
    df.to_file(os.path.join(output_path, "PredictedBirds.shp"))

    # Write output as csv
    grouped_df = df.groupby(['Site', 'Date', 'label']).size().reset_index(name='count')
    csv_file_path = os.path.join(output_path, "PredictedBirds.csv")
    grouped_df.to_csv(csv_file_path, index=False)

    # Zip the shapefile for storage efficiency
    with ZipFile(output_zip, 'w', ZIP_DEFLATED) as zip:
        for ext in ['cpg', 'dbf', 'prj', 'shp', 'shx']:
            focal_file = os.path.join(output_path, f"PredictedBirds.{ext}")
            file_name = os.path.basename(focal_file)
            zip.write(focal_file, arcname=file_name)
            os.remove(focal_file)

    # Copy PredictedBirds.zip to everglades-forecast-web repo
    dest_path = "/blue/ewhite/everglades/everglades-forecast-web/data"
    if not os.path.exists(dest_path):
        os.makedirs(dest_path)
    dest_file = os.path.join(dest_path, "PredictedBirds.zip")

    if os.path.exists(output_zip):
        shutil.copy(output_zip, dest_file)
        print(f"{output_zip} copied to {dest_file}.")
    else:
        print("{output_zip} file does not exist.")
