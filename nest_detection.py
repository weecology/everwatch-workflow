# Bird Bird Bird Detector
# Given a set of predictions in /orange/ewhite/everglades/predictions/, generate predicted nests
import os
import sys
import glob
from pathlib import Path

import pandas as pd
import geopandas

import tools

SCHEMA = {
    "geometry": "Point",
    "properties": {
        "nest_id": "int",
        "Site": "str",
        "Year": "str",
        "xmean": "float",
        "ymean": "float",
        "first_obs": "str",
        "last_obs": "str",
        "num_obs": "int",
        "species": "str",
        "sum_top1": "float",
        "num_top1": "int",
        "bird_match": "str",
    },
}


def calculate_IoUs(geom, match):
    """Calculate intersection-over-union scores for a pair of boxes"""
    intersection = geom.intersection(match).area
    union = geom.union(match).area
    iou = intersection / float(union)
    return iou


def compare_site(gdf):
    """Iterate over a dataframe and check rows"""
    results = []
    claimed_indices = []
    spatial_index = gdf.sindex

    for index, row in gdf.iterrows():
        if index in claimed_indices:
            continue
        claimed_indices.append(index)
        geom = row["geometry"]

        possible_matches_index = list(spatial_index.intersection(geom.bounds))
        possible_matches = gdf.iloc[possible_matches_index]

        # Remove matches to the current date, which are nearby birds not the same bird on a different date
        possible_matches = possible_matches.loc[possible_matches["Date"] != row.Date]

        # Check for multiple matches from the same date and pick best match
        match_date_count = possible_matches.groupby("Date").Date.agg("count")
        multiple_match_dates = match_date_count[match_date_count > 1]

        if not multiple_match_dates.empty:
            for date in multiple_match_dates.index:
                mm = possible_matches[possible_matches["Date"] == date].copy()
                mm = mm.assign(iou=mm["geometry"].map(lambda x: calculate_IoUs(x, geom)))
                best_match = mm.loc[mm["iou"] == mm["iou"].max()].drop(columns="iou")
                possible_matches = possible_matches.drop(possible_matches[possible_matches["Date"] == date].index)
                possible_matches = geopandas.GeoDataFrame(pd.concat([possible_matches, best_match], ignore_index=True),
                                                          crs=gdf.crs)

        # remove matches already claimed
        matches = possible_matches[~(possible_matches.index.isin(claimed_indices))]
        if matches.empty:
            continue

        # add to claimed
        claimed_indices.extend(matches.index.values)

        # add target info to match
        row_gdf = geopandas.GeoDataFrame(pd.DataFrame(row).transpose(), crs=matches.crs)
        matches = geopandas.GeoDataFrame(pd.concat([matches, row_gdf], ignore_index=True), crs=matches.crs)
        matches["target_ind"] = index
        matches = matches.rename(columns={
            "xmin": "match_xmin",
            "xmax": "match_xmax",
            "ymin": "match_ymin",
            "ymax": "match_ymax",
        })
        results.append(matches)

    if results:
        results = pd.concat(results, ignore_index=True)
    else:
        results = pd.DataFrame(columns=list(SCHEMA["properties"].keys()))
    return results


def detect_nests(bird_detection_file, year, site, savedir):
    """Given a set of shapefiles, track time series of overlaps and save a shapefile of detected boxes"""
    os.makedirs(savedir, exist_ok=True)
    filename = os.path.join(savedir, f"{site}_{year}_detected_nests.shp")
    df = geopandas.read_file(bird_detection_file)

    # In some versions of DeepForest, when image coordinates are reprojected
    # to geographic coordinates the columns storing the bounding box positions
    # are not updated. This code ensures that the bounding box columns we use
    # match the properly transformed geometry.
    df["xmin"] = df.geometry.bounds["minx"]
    df["ymin"] = df.geometry.bounds["miny"]
    df["xmax"] = df.geometry.bounds["maxx"]
    df["ymax"] = df.geometry.bounds["maxy"]
    results = compare_site(df)

    gdf_tofile = None
    if not results.empty:
        results["Site"] = site
        results["Year"] = year
        result_shp = geopandas.GeoDataFrame(results, crs=df.crs)
        gdf_tofile = result_shp
    else:
        empty_data = {
            k: pd.Series(dtype="int64" if v == "int" else "float64" if v == "float" else "object")
            for k, v in SCHEMA["properties"].items()
        }
        empty_results = geopandas.GeoDataFrame(
            empty_data,
            geometry=geopandas.GeoSeries([], dtype="geometry"),
            crs=df.crs,
        )
        gdf_tofile = empty_results

    try:
        import pyogrio
        gdf_tofile.to_file(filename, driver="ESRI Shapefile", engine="pyogrio")
    except ImportError:
        gdf_tofile.to_file(filename, driver="ESRI Shapefile", engine="fiona")

    return filename


if __name__ == "__main__":
    working_dir = tools.get_working_dir()
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]
    savedir = os.path.join(working_dir, "detected_nests", year, site)
    detect_nests(path, year, site, savedir=savedir)
