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


def project(raster_path, boxes):
    """
    Convert image coordinates into a geospatial object to overlap with input image. 
    Args:
        raster_path: path to the raster .tif on disk. Assumed to have a valid spatial projection
        boxes: a prediction pandas dataframe from deepforest.predict_tile()
    Returns:
        a geopandas dataframe with predictions in input projection.
    """
    with rasterio.open(raster_path) as dataset:
        bounds = dataset.bounds
        pixelSizeX, pixelSizeY = dataset.res

    # subtract origin. Recall that numpy origin is top left! Not bottom left.
    boxes["xmin"] = (boxes["xmin"] * pixelSizeX) + bounds.left
    boxes["xmax"] = (boxes["xmax"] * pixelSizeX) + bounds.left
    boxes["ymin"] = bounds.top - (boxes["ymin"] * pixelSizeY)
    boxes["ymax"] = bounds.top - (boxes["ymax"] * pixelSizeY)

    # create geometry column
    boxes['geometry'] = boxes.apply(lambda x: shapely.geometry.box(x.xmin, x.ymin, x.xmax, x.ymax), axis=1)

    # drop unnecessary columns
    boxes = boxes.drop(columns=['xmin', 'ymin', 'xmax', 'ymax'])

    # Create a GeoDataFrame
    gdf = geopandas.GeoDataFrame(boxes, geometry='geometry')

    return gdf


def run(proj_tile_path, checkpoint_path, savedir="."):
    """Apply trained model to a drone tile"""

    # generate label dict using same code as for fitting
    split_checkpoint_path = os.path.normpath(checkpoint_path).split(os.path.sep)
    timestamp = split_checkpoint_path[-2]
    train = pd.read_csv(f"/blue/ewhite/everglades/Zooniverse/parsed_images/species_train_{timestamp}.csv")
    label_dict = {key: value for value, key in enumerate(train.label.unique())}

    # create the model and load the weights for the fitted model
    checkpoint = torch.load(checkpoint_path, map_location="cpu")  # map_location is necessary for successful load

    model = main.deepforest(num_classes=len(label_dict), label_dict=label_dict)
    model.create_trainer(enable_progress_bar=False)
    model.load_state_dict(checkpoint["state_dict"])

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
    checkpoint_path = "/blue/ewhite/everglades/Zooniverse/20220910_182547/species_model.pl"

    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]

    working_dir = tools.get_working_dir()
    savedir = os.path.join(working_dir, "predictions", year, site)
    result = run(proj_tile_path=path, checkpoint_path=checkpoint_path, savedir=savedir)
