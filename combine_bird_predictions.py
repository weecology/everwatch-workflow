import geopandas
import glob
import os
import pandas as pd
import re
from zipfile import ZipFile
from zipfile import ZIP_DEFLATED

def find_shp_files(predictions_path):
    files = glob.glob(os.path.join(predictions_path, '**', '**', '*_projected.shp'))
    return(files)

def get_site(path):
    path = os.path.basename(path)    
    regex = re.compile("(\\w+)_\\d+_\\d+_\\d+.*_projected")
    return regex.match(path).group(1)

def get_event(path):
    path = os.path.basename(path)
    regex = re.compile('\\w+_(\\d+_\\d+_\\d+).*_projected')
    return regex.match(path).group(1)

def load_shapefile(x):
    print(x)
    shp = geopandas.read_file(x)
    shp["site"] = get_site(x)
    shp["event"] = get_event(x)
    return shp

def combine(paths, score_thresh):
    """Take prediction shapefiles and wrap into a single file"""
    shapefiles = []
    for x in paths:
        try:
            shapefiles.append(load_shapefile(x))
        except:
            print(f"Mistructured file path: {x}. File not added to PredictedBirds.shp")
    summary = geopandas.GeoDataFrame(pd.concat(shapefiles,ignore_index=True),crs=shapefiles[0].crs)
    summary = summary[summary.score > score_thresh]
    
    return summary

if __name__ == "__main__":
    score_thresh = 0.3
    predictions_path = "/blue/ewhite/everglades/predictions/"
    output_path = "/blue/ewhite/everglades/EvergladesTools/App/Zooniverse/data/"

    predictions = find_shp_files(predictions_path)
    #write output to zooniverse app
    df = combine(predictions, score_thresh)
    df.to_file(os.path.join(output_path, "PredictedBirds.shp"))

    # Zip the shapefile for storage efficiency
    with ZipFile("../App/Zooniverse/data/PredictedBirds.zip", 'w', ZIP_DEFLATED) as zip:
        for ext in ['cpg', 'dbf', 'prj', 'shp', 'shx']:
            focal_file = os.path.join(output_path, f"PredictedBirds.{ext}")
            file_name = os.path.basename(focal_file)
            zip.write(focal_file, arcname=file_name)
            os.remove(focal_file)
