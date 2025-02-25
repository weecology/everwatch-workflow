import os
import sys
import tools

import geopandas
import pandas as pd
import rasterio
import shapely
import torch
from deepforest import main
from deepforest.utilities import boxes_to_shapefile


def run(proj_tile_path, savedir="."):
    """Apply trained model to a drone tile"""

    model = main.deepforest()
    model.load_model("weecology/everglades-bird-species-detector")

    boxes = model.predict_tile(raster_path=proj_tile_path, patch_overlap=0, patch_size=1500)
    proj_tile_dir = os.path.dirname(proj_tile_path)
    projected_boxes = boxes_to_shapefile(boxes, proj_tile_dir)
    if not os.path.exists(savedir):
        os.makedirs(savedir)
    basename = os.path.splitext(os.path.basename(proj_tile_path))[0]
    fn = "{}/{}.shp".format(savedir, basename)
    # Write GeoDataFrame to a new shapefile (avoid appending)
    projected_boxes.to_file(fn, driver="ESRI Shapefile")
    return fn


if __name__ == "__main__":
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]

    working_dir = tools.get_working_dir()
    savedir = os.path.join(working_dir, "predictions", year, site)
    result = run(proj_tile_path=path, savedir=savedir)
