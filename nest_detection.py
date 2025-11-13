# Bird Bird Bird Detector
# Given a set of predictions in /orange/ewhite/everglades/predictions/, generate predicted nests
import os
import sys
import glob
from pathlib import Path

import pandas as pd
import geopandas
# Force the Fiona engine if you prefer (schema supported by Fiona):
# geopandas.options.io_engine = "fiona"

import tools

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

        # remove same-date matches
        possible_matches = possible_matches.loc[possible_matches["Date"] != row.Date]

        # if multiple matches on a date, keep best IoU
        match_date_count = possible_matches.groupby("Date").Date.agg("count")
        multiple_match_dates = match_date_count[match_date_count > 1]

        if not multiple_match_dates.empty:
            for date in multiple_match_dates.index:
                # makes a real, independent copy of those rows
                mm = possible_matches[possible_matches["Date"] == date].copy()
                mm = mm.assign(iou=mm["geometry"].map(lambda x: calculate_IoUs(x, geom)))
                # mm["iou"].max() computes the maximum directly from that Series
                best_match = mm.loc[mm["iou"] == mm["iou"].max()].drop(columns="iou")
                possible_matches = possible_matches.drop(
                    possible_matches[possible_matches["Date"] == date].index
                )
                possible_matches = geopandas.GeoDataFrame(
                    pd.concat([possible_matches, best_match], ignore_index=True),
                    crs=gdf.crs
                )

        # remove matches already claimed
        matches = possible_matches[~(possible_matches.index.isin(claimed_indices))]
        if matches.empty:
            continue

        claimed_indices.extend(matches.index.values)

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
        results = pd.DataFrame(columns=[
            "match_xmin", "match_ymin", "match_xmax", "match_ymax",
            "label", "score", "image_path", "Site", "Date", "Year",
            "event", "file_posts", "bird_id", "target_ind"
        ])
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

    if not results.empty:
        results["Site"] = site
        results["Year"] = year
        result_shp = geopandas.GeoDataFrame(results, crs=df.crs)
        # Let the engine infer schema (pyogrio doesn’t accept `schema=...`)
        result_shp.to_file(filename, driver="ESRI Shapefile")
    else:
        # Create a truly empty GeoDataFrame with dtypes so schema can be inferred
        dtypes = {
            "match_xmin": "float64", "match_ymin": "float64",
            "match_xmax": "float64", "match_ymax": "float64",
            "label": "object", "score": "float64", "image_path": "object",
            "Site": "object", "Date": "object", "Year": "object",
            "event": "object", "file_posts": "object",
            "bird_id": "int32", "target_ind": "int32",
        }
        data = {k: pd.Series(dtype=v) for k, v in dtypes.items()}
        empty_results = geopandas.GeoDataFrame(data, geometry=geopandas.GeoSeries([], dtype="geometry"), crs=df.crs)
        empty_results.to_file(filename, driver="ESRI Shapefile")
    return filename

# The rest of your functions (find_rgb_paths, crop, crop_images, etc.) unchanged…

if __name__ == "__main__":
    working_dir = tools.get_working_dir()
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]
    savedir = os.path.join(working_dir, "detected_nests", year, site)
    detect_nests(path, year, site, savedir=savedir)