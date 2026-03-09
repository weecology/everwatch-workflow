import os
import sys
import tools

import geopandas
import pandas as pd
import rasterio
import torch
from deepforest import main
from deepforest.utilities import image_to_geo_coordinates
import PIL.Image

PIL.Image.MAX_IMAGE_PIXELS = None


def run(proj_tile_path, savedir="."):
    """Apply trained model to a drone tile"""
    model_name = "weecology/everglades-bird-species-detector"
    model = main.deepforest()
    model.load_model(model_name=model_name)

    with rasterio.open(proj_tile_path) as src:
        raster_crs = src.crs

    boxes = model.predict_tile(
        path=proj_tile_path,
        patch_overlap=0,
        patch_size=1500,
        dataloader_strategy="window",
    )
    proj_tile_dir = os.path.dirname(proj_tile_path)
    projected_boxes = None
    if boxes is not None:
        projected_boxes = image_to_geo_coordinates(boxes, proj_tile_dir)
    else:
        projected_boxes = geopandas.GeoDataFrame(
            {
                "xmin": pd.Series(dtype="float64"),
                "ymin": pd.Series(dtype="float64"),
                "xmax": pd.Series(dtype="float64"),
                "ymax": pd.Series(dtype="float64"),
                "label": pd.Series(dtype="object"),
                "score": pd.Series(dtype="float64"),
                "image_path": pd.Series(dtype="object"),
            },
            geometry=geopandas.GeoSeries([], dtype="geometry"),
            crs=raster_crs,
        )

    os.makedirs(savedir, exist_ok=True)
    basename = os.path.splitext(os.path.basename(proj_tile_path))[0]
    fn = "{}/{}.shp".format(savedir, basename)

    try:
        import pyogrio
        projected_boxes.to_file(fn, driver="ESRI Shapefile", engine="pyogrio")
    except ImportError:
        projected_boxes.to_file(fn, driver="ESRI Shapefile", engine="fiona")
    return fn


if __name__ == "__main__":
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]

    working_dir = tools.get_working_dir()
    savedir = os.path.join(working_dir, "predictions", year, site)
    result = run(proj_tile_path=path, savedir=savedir)
