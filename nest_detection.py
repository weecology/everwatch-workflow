# Bird Bird Bird Detector
# Given a set of predictions in /orange/ewhite/everglades/predictions/, generate predicted nests
import glob
import os
import random
from pathlib import Path
from zipfile import ZIP_DEFLATED
from zipfile import ZipFile

import cv2
import geopandas
import numpy as np
import pandas as pd
import rasterio
from PIL import Image, ImageDraw
from panoptes_client import SubjectSet, Subject
from rasterio.windows import from_bounds

def load_files(dirname, year, site):
    """Load shapefiles and concat into large frame"""
    shapefiles = glob.glob(dirname + "*.shp")

    # load all shapefiles to create a dataframe
    df = []
    for x in shapefiles:
        try:
            # Catch and skip badly structured file names
            # TODO: fix file naming issues so we don't need this
            print(x)
            eventdf = geopandas.read_file(x)
            eventdf["Site"] = site
            eventdf["Date"] = get_date(x)
            eventdf["Year"] = year
            df.append(eventdf)
        except IndexError as e:
            print("Filename issue:")
            print(e)
    df = geopandas.GeoDataFrame(pd.concat(df, ignore_index=True))
    df.crs = eventdf.crs

    return df

def get_date(x):
    """parse filename to return event name"""
    basename = os.path.basename(x)
    event = basename.split("_")[1:4]
    event = "_".join(event)

    return event

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

    # Create spatial index
    spatial_index = gdf.sindex

    for index, row in gdf.iterrows():
        # skip is already claimed
        if index in claimed_indices:
            continue

        claimed_indices.append(index)
        geom = row["geometry"]

        # Look up matches
        possible_matches_index = list(spatial_index.intersection(geom.bounds))
        possible_matches = gdf.iloc[possible_matches_index]

        # Remove matches to the current date, which are nearby birds not the same bird on a different date
        possible_matches = possible_matches.loc[possible_matches['Date'] != row.Date]

        # Check for multiple matches from the same date and pick best match
        match_date_count = possible_matches.groupby('Date').Date.agg('count')
        multiple_match_dates = match_date_count[match_date_count > 1]

        if not multiple_match_dates.empty:
            for date in multiple_match_dates.index:
                multiple_matches = possible_matches[possible_matches['Date'] == date]
                multiple_matches = multiple_matches.assign(
                    iou=multiple_matches['geometry'].map(lambda x: calculate_IoUs(x, geom)))
                best_match = multiple_matches[multiple_matches["iou"] == max(multiple_matches['iou'])].drop('iou',
                                                                                                            axis=1)
                possible_matches = possible_matches.drop(possible_matches[possible_matches['Date'] == date].index)
                possible_matches = possible_matches.append(best_match)

        # Remove any matches that are claimed by another nest detection
        matches = possible_matches[~(possible_matches.index.isin(claimed_indices))]

        if matches.empty:
            continue

        # add to claimed
        claimed_indices.extend(matches.index.values)

        # add target info to match
        matches = matches.append(row)
        matches["target_index"] = index
        matches = matches.rename(
            columns={"xmin": "matched_xmin", "max": "matched_xmax", "ymin": "matched_ymin", "ymax": "matched_ymax"})

        results.append(matches)

    if len(results) == 0:
        return None

    results = pd.concat(results)

    return results

def detect_nests(dirname, year, site, savedir):
    """Given a set of shapefiles, track time series of overlaps and save a shapefile of detected boxes"""

    df = load_files(dirname, year, site)
    df = df.assign(bird_id = range(len(df)))
    results = compare_site(df)
    results["Site"] = site
    results["Year"] = year

    result_shp = geopandas.GeoDataFrame(results)
    result_shp.crs = df.crs

    if not os.path.exists(savedir):
        os.makedirs(savedir)
    filename = os.path.join(savedir, f"{site}_{year}_detected_nests.shp")
    result_shp.to_file(filename)

    return filename


def find_rgb_paths(site, paths):
    paths = [x for x in paths if site in x]
    paths.sort()

    return paths


def crop(rgb_path, geom, extend_box=3):
    src = rasterio.open(rgb_path)
    left, bottom, right, top = geom.bounds
    window = from_bounds(left - extend_box,
                         bottom - extend_box,
                         right + extend_box,
                         top + extend_box,
                         transform=src.transform)

    numpy_array = src.read(window=window)
    numpy_array_rgb = np.rollaxis(numpy_array, 0, 3)
    numpy_array_bgr = numpy_array_rgb[:, :, ::-1]
    return numpy_array_bgr


def crop_images(df, rgb_images):
    """Crop images for a series of data"""
    crops = {}
    geom = df.geometry.iloc[0]
    target_ind = df.target_ind.unique()[0]

    for tile in rgb_images:
        # find rgb data
        basename = os.path.splitext(os.path.basename(tile))[0]
        datename = "{}_{}".format(target_ind, basename)
        crops[datename] = crop(tile, geom)

    return crops


def create_subject(filenames, everglades_watch):
    subject = Subject()

    subject.links.project = everglades_watch
    print("adding subjects: {}".format(filenames))
    for filename in filenames:
        subject.add_location(filename)
        subject.metadata.update({"filename": filename})

    # Trigger upload
    subject.save()

    return subject


def create_subject_set(everglades_watch, name="Nest detections 2.0"):
    subject_set = SubjectSet()
    subject_set.links.project = everglades_watch
    subject_set.display_name = name
    subject_set.save()

    return subject_set


def write_timestamp(image, text):
    text = text.replace("_projected", "")
    image = Image.fromarray(image)
    draw = ImageDraw.Draw(image)
    draw.text((10, 10), text)
    return np.array(image)


def extract_nests(filename, rgb_pool, savedir, upload=False):
    gdf = geopandas.read_file(filename)
    grouped = gdf.groupby("target_ind")
    if upload:
        everglades_watch = utils.connect()
        subject_set = create_subject_set(everglades_watch)
        subjects = []

    for name, group in grouped:
        # atleast three detections
        if group.shape[0] < 3:
            continue

        # Crop with date names as key
        site = group.Site.unique()[0]
        rgb_images = find_rgb_paths(site, rgb_pool)
        crops = crop_images(group, rgb_images=rgb_images)

        # save output
        dirname = "{}/{}_{}".format(savedir, name, group["Site"].unique()[0])
        if not os.path.exists(dirname):
            os.mkdir(dirname)

        filenames = []
        for datename in crops:
            filename = "{}/{}.png".format(dirname, datename)
            crop = crops[datename]
            if not crop.shape[2] == 3:
                print(f"[SKIP] Crop does not have three channels: {filename}")
                continue
            if (crop.shape[0] == 0) or (crop.shape[1] == 0):
                print(f"[SKIP] Crop overlaps edge of tile: {filename}")
                continue

            cv2.imwrite(filename, crop)
            filenames.append(filename)

        if upload:
            subject = create_subject(filenames, everglades_watch)
            subjects.append(subject)

    if upload:
        random.shuffle(subjects)
        subject_set.add(subjects)


def find_files():
    paths = glob.glob("/orange/ewhite/everglades/utm_projected/*.tif")
    paths = [x for x in paths if not "Cypress" in x]
    paths = [x for x in paths if not "Joule_05_05_2021" in x]  # Joul 05_05_2021 is current not projected properly

    return paths


if __name__ == "__main__":
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]
    savedir = os.path.join("/blue/ewhite/everglades/detected_nests/", year, site)
    detect_nests(path, year, site, savedir=savedir)

    with ZipFile("../App/Zooniverse/data/nest_detections_processed.zip", 'w', ZIP_DEFLATED) as zip:
        for ext in ['.cpg', '.dbf', '.prj', '.shp', '.shx']:
            focal_file = processed_nests_shp.with_suffix(ext)
            file_name = focal_file.name
            zip.write(focal_file, arcname=file_name)
            os.remove(focal_file)
