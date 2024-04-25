# Bird Bird Bird Detector
# Given a set of predictions in /orange/ewhite/everglades/predictions/, generate predicted nests
import glob
import os
from pathlib import Path
import geopandas
import pandas as pd
import sys

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
                possible_matches = geopandas.GeoDataFrame(pd.concat([possible_matches, best_match], ignore_index=True))

        # Remove any matches that are claimed by another nest detection
        matches = possible_matches[~(possible_matches.index.isin(claimed_indices))]

        if matches.empty:
            continue

        # add to claimed
        claimed_indices.extend(matches.index.values)

        # add target info to match
        row = geopandas.GeoDataFrame(pd.DataFrame(row).transpose(), crs=matches.crs)
        matches = geopandas.GeoDataFrame(pd.concat([matches, row], ignore_index=True))
        matches["target_ind"] = index
        matches = matches.rename(columns={
            "xmin": "match_xmin",
            "xmax": "match_xmax",
            "ymin": "match_ymin",
            "ymax": "match_ymax"
        })

        results.append(matches)

    if results:
        results = pd.concat(results)
    else:
        results = pd.DataFrame(columns=[
            'match_xmin', 'match_ymin', 'match_xmax', 'match_ymax', 'label', 'score', 'image_path', 'Site', 'Date',
            'Year', 'event', 'file_posts', 'bird_id', 'target_ind'
        ])

    return results


def detect_nests(bird_detection_file, year, site, savedir):
    """Given a set of shapefiles, track time series of overlaps and save a shapefile of detected boxes"""

    if not os.path.exists(savedir):
        os.makedirs(savedir)
    filename = os.path.join(savedir, f"{site}_{year}_detected_nests.shp")
    df = geopandas.read_file(bird_detection_file)

    results = compare_site(df)

    schema = {
        "geometry": "Polygon",
        "properties": {
            'match_xmin': 'float',
            'match_ymin': 'float',
            'match_xmax': 'float',
            'match_ymax': 'float',
            'label': 'str',
            'score': 'float',
            'image_path': 'str',
            'Site': 'str',
            'Date': 'str',
            'Year': 'str',
            'event': 'str',
            'file_posts': 'str',
            'bird_id': 'int',
            'target_ind': 'int'
        }
    }
    if not results.empty:
        results["Site"] = site
        results["Year"] = year
        result_shp = geopandas.GeoDataFrame(results)
        result_shp.crs = df.crs
        result_shp.to_file(filename, schema=schema)
    else:
        crs = df.crs
        empty_results = geopandas.GeoDataFrame(geometry=[])
        empty_results.to_file(filename, driver='ESRI Shapefile', schema=schema, crs=crs)

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


if __name__ == "__main__":
    working_dir = tools.get_working_dir()
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]
    savedir = os.path.join(working_dir, "detected_nests", year, site)
    detect_nests(path, year, site, savedir=savedir)
