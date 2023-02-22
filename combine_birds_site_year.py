import os
import sys

import geopandas
import pandas as pd

import tools


def combine_files(bird_detection_files, year, site, score_thresh, savedir):
    """Load shapefiles and concat into large frame"""
    # load all shapefiles to create a dataframe
    df = []
    for x in bird_detection_files:
        try:
            # Catch and skip badly structured file names
            # TODO: fix file naming issues so we don't need this
            eventdf = geopandas.read_file(x)
            eventdf["Site"] = tools.get_site(x)
            eventdf["Date"] = tools.get_date(x)
            eventdf["Year"] = tools.get_year(x)
            eventdf["event"] = tools.get_event(x)
            eventdf = eventdf[eventdf.score > score_thresh]
            df.append(eventdf)
        except IndexError as e:
            print("Filename issue:")
            print(e)
    df = geopandas.GeoDataFrame(pd.concat(df, ignore_index=True))
    df.crs = eventdf.crs
    df = df.assign(bird_id=range(1, len(df) + 1))  # Index bird IDs starting at 1
    filename = os.path.join(savedir, f"{site}_{year}_combined.shp")
    df.to_file(filename)

    return df


if __name__ == "__main__":
    score_thresh = 0.3
    paths = sys.argv[1:]
    split_path = os.path.normpath(paths[0]).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]
    savedir = os.path.join("/blue/ewhite/everglades/predictions/", year, site)
    combine_files(paths, year, site, score_thresh, savedir=savedir)
