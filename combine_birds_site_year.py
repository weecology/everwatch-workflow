import os
import sys

import geopandas
import pandas as pd
from shapely.errors import GEOSException

import tools


def combine_files(bird_detection_files, year, site, score_thresh, savedir):
    """Load shapefiles and concat into large frame"""
    # load all shapefiles to create a dataframe
    df = []
    for x in bird_detection_files:
        try:
            # Catch and skip badly structured file names
            # TODO: fix file naming issues so we don't need this
            try:
                eventdf = geopandas.read_file(x)
                # Fix any invalid geometries
                if len(eventdf) > 0:
                    invalid_mask = ~eventdf.geometry.is_valid
                    if invalid_mask.any():
                        eventdf.loc[invalid_mask, 'geometry'] = eventdf.loc[invalid_mask, 'geometry'].make_valid()
            except (GEOSException, ValueError) as geom_error:
                print(f"Warning: Could not read {x} due to geometry error, skipping...")
                continue

            # Skip empty files
            if len(eventdf) == 0:
                continue

            eventdf["Site"] = tools.get_site(x)
            eventdf["Date"] = tools.get_date(x)
            eventdf["Year"] = tools.get_year(x)
            eventdf["event"], eventdf["file_postscript"] = tools.get_event(x)
            eventdf = eventdf[eventdf.score > score_thresh]
            df.append(eventdf)
        except IndexError as e:
            print("Filename issue:")
            print(e)
    if not df:
        return None
    df = geopandas.GeoDataFrame(pd.concat(df, ignore_index=True))
    df = df.assign(bird_id=range(1, len(df) + 1))  # Index bird IDs starting at 1

    # Rename columns to comply with ESRI Shapefile 10-character limit
    # This avoids warnings about truncation
    column_rename = {}
    for col in df.columns:
        if len(col) > 10:
            column_rename[col] = col[:10]
    if column_rename:
        df = df.rename(columns=column_rename)

    filename = os.path.join(savedir, f"{site}_{year}_combined.shp")
    print(filename)

    try:
        import pyogrio
        df.to_file(filename, driver="ESRI Shapefile", engine="pyogrio")
    except ImportError:
        df.to_file(filename, driver="ESRI Shapefile", engine="fiona")

    return df


if __name__ == "__main__":
    score_thresh = 0.3
    paths = sys.argv[1:]
    split_path = os.path.normpath(paths[0]).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]

    working_dir = tools.get_working_dir()
    savedir = os.path.join(working_dir, "predictions", year, site)
    combine_files(paths, year, site, score_thresh, savedir=savedir)
