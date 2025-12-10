import os
import sys
import tools

import geopandas
import pandas as pd
import rasterio
import torch
from deepforest import main
from deepforest.utilities import image_to_geo_coordinates, load_config
import PIL.Image

PIL.Image.MAX_IMAGE_PIXELS = None


def run(proj_tile_path, savedir="."):
    """Apply trained model to a drone tile"""
    
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    config = load_config(config_path)
    model = main.deepforest(config=config)

    boxes = model.predict_tile(path=proj_tile_path, patch_overlap=0, patch_size=1500)
    proj_tile_dir = os.path.dirname(proj_tile_path)
    if boxes is None:
        print(f"No boxes found for {proj_tile_path}")
        return None
    projected_boxes = image_to_geo_coordinates(boxes, proj_tile_dir)
    
    # Get CRS from raster file for empty case
    with rasterio.open(proj_tile_path) as src:
        raster_crs = src.crs
    
    os.makedirs(savedir, exist_ok=True)
    basename = os.path.splitext(os.path.basename(proj_tile_path))[0]
    fn = "{}/{}.shp".format(savedir, basename)

    gdf_tofile = None
    if len(projected_boxes) > 0:
        # image_to_geo_coordinates isn't currently updating the columns,
        # just the geometry, so update the columns ourselves
        projected_boxes["xmin"] = projected_boxes.geometry.bounds["minx"]
        projected_boxes["ymin"] = projected_boxes.geometry.bounds["miny"]
        projected_boxes["xmax"] = projected_boxes.geometry.bounds["maxx"]
        projected_boxes["ymax"] = projected_boxes.geometry.bounds["maxy"]
        gdf_tofile = projected_boxes
    else:
        # Create empty GeoDataFrame with expected schema
        empty_data = {
            'xmin': pd.Series(dtype='float64'),
            'ymin': pd.Series(dtype='float64'),
            'xmax': pd.Series(dtype='float64'),
            'ymax': pd.Series(dtype='float64'),
            'label': pd.Series(dtype='object'),
            'score': pd.Series(dtype='float64'),
            'image_path': pd.Series(dtype='object')
        }
        empty_gdf = geopandas.GeoDataFrame(empty_data,
                                           geometry=geopandas.GeoSeries([], dtype="geometry"),
                                           crs=raster_crs)
        gdf_tofile = empty_gdf

    try:
        import pyogrio
        gdf_tofile.to_file(fn, driver="ESRI Shapefile", engine="pyogrio")
    except ImportError:
        gdf_tofile.to_file(fn, driver="ESRI Shapefile", engine="fiona")
    return fn


if __name__ == "__main__":
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]

    working_dir = tools.get_working_dir()
    savedir = os.path.join(working_dir, "predictions", year, site)
    result = run(proj_tile_path=path, savedir=savedir)
