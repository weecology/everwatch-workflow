#Bird Bird Bird Detector
# Given a set of predictions in /orange/ewhite/everglades/predictions/, generate predicted nests
import glob
import geopandas
import rtree
import rasterio
import random
import os
import pandas as pd
import cv2
import numpy as np
from panoptes_client import Panoptes, Project, SubjectSet, Subject
import utils
from zipfile import ZipFile
from zipfile import ZIP_DEFLATED
from pathlib import Path

from rasterio.windows import from_bounds
from PIL import Image, ImageDraw

def load_files(dirname):
    """Load shapefiles and concat into large frame"""
    shapefiles = glob.glob(dirname + "*.shp")
    
    #load all shapefiles to create a dataframe
    df = []
    for x in shapefiles:
        try:
        # Catch and skip badly structured file names
        # TODO: fix file naming issues so we don't need this
            print(x)
            eventdf = geopandas.read_file(x)
            eventdf["Site"] = get_site(x)
            eventdf["Date"] = get_date(x)
            eventdf["Year"] = get_year(x)
            df.append(eventdf)
        except IndexError as e:
            print("Filename issue:")
            print(e)
    df = geopandas.GeoDataFrame(pd.concat(df, ignore_index=True))
    df.crs = eventdf.crs
    
    return df
    
def get_site(x):
    """parse filename to return site name"""
    basename = os.path.basename(x)
    site = basename.split("_")[0]
    return site

def get_date(x):
    """parse filename to return event name"""
    basename = os.path.basename(x)
    event = basename.split("_")[1:4]
    event = "_".join(event)
    
    return event

def get_year(x):
    "parse filename to return the year of sampling"
    basename = os.path.basename(x)
    year = basename.split("_")[3]
    return year

def compare_site(gdf):
    """Iterate over a dataframe and check rows"""
    results = []
    claimed_indices = []
    
    #Create spatial index
    spatial_index = gdf.sindex
    
    for index, row in gdf.iterrows():
        #skip is already claimed
        if index in claimed_indices:
            continue
            
        claimed_indices.append(index)
        geom = row["geometry"]
        
        #Look up matches
        possible_matches_index = list(spatial_index.intersection(geom.bounds))
        possible_matches = gdf.iloc[possible_matches_index]

        #Remove matches to the current date, which are nearby birds not the same bird on a different date
        possible_matches = possible_matches.loc[possible_matches['Date'] != row.Date]
        
        #Remove any matches that are claimed by another nest detection
        matches = possible_matches[~(possible_matches.index.isin(claimed_indices))]
        
        if matches.empty:
            continue
        
        #add to claimed
        claimed_indices.extend(matches.index.values)
        
        #add target info to match
        matches = matches.append(row)
        matches["target_index"] = index
        matches = matches.rename(columns={"xmin":"matched_xmin","max":"matched_xmax","ymin":"matched_ymin","ymax":"matched_ymax"})

        results.append(matches)
    
    if len(results) == 0:
        return None
        
    results = pd.concat(results)
    
    return results
        
def check_overlap(geom, gdf):
    """Find spatially overlapping rows between target and pool of geometries"""
    matches = gdf.intersects(geom)
    
    return matches
    
def detect_nests(dirname, savedir):
    """Given a set of shapefiles, track time series of overlaps and save a shapefile of detected boxes"""
    
    df = load_files(dirname)
        
    grouped = df.groupby(["Site", "Year"])
    results = []
    for name, group in grouped:
        print(f"Processing {name}")
        site_results = compare_site(group)
        if site_results is not None:
            site_results["Site"] = name[0]
            site_results["Year"] = name[1]
            results.append(site_results)
    
    result_shp = geopandas.GeoDataFrame(pd.concat(results, ignore_index=True))
    result_shp.crs = df.crs
    
    filename = "{}/nest_detections.shp".format(savedir)
    result_shp.to_file(filename)

    return filename

def process_nests(nest_file, savedir, min_score=0.4, min_detections=3):
    """Process nests into a one row per nest table"""
    nests_data = geopandas.read_file(nest_file)
    target_inds = nests_data['target_ind'].unique()
    nests = []
    for target_ind in target_inds:
        nest_data = nests_data[(nests_data['target_ind'] == target_ind) & (nests_data['score'] >= min_score)]
        if len(nest_data) >= min_detections:
            summed_scores = nest_data.groupby(['Site', 'Year', 'target_ind', 'label']).score.agg(['sum', 'count'])
            top_score_data = summed_scores[summed_scores['sum'] == max(summed_scores['sum'])].reset_index()
            nest_info = nest_data.groupby(['Site', 'Year', 'target_ind']).agg({'Date': ['min', 'max', 'count'], 
                                                                            'matched_xm': ['mean'],
                                                                            'matched_ym': ['mean']}).reset_index()
            nests.append([target_ind,
                        nest_info['Site'][0],
                        nest_info['Year'][0],
                        nest_info['matched_xm']['mean'][0],
                        nest_info['matched_ym']['mean'][0],
                        nest_info['Date']['min'][0],
                        nest_info['Date']['max'][0],
                        nest_info['Date']['count'][0],
                        top_score_data['label'][0],
                        top_score_data['sum'][0],
                        top_score_data['count'][0]])

    nests = pd.DataFrame(nests, columns=['nest_id', 'Site', 'Year', 'matched_xm', 'matched_ym',
                                'first_obs', 'last_obs', 'num_obs',
                                'species', 'sum_top1_score', 'num_obs_top1'])
    nests_shp = geopandas.GeoDataFrame(nests,
                                       geometry=geopandas.points_from_xy(nests.matched_xm, nests.matched_ym))
    nests_shp.crs = nests_data.crs
    save_path = f"{savedir}/nest_detections_processed.shp"
    nests_shp.to_file(save_path)
    return(save_path)

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
    numpy_array_rgb = np.rollaxis(numpy_array, 0,3)    
    numpy_array_bgr = numpy_array_rgb[:,:,::-1]    
    return numpy_array_bgr
    
def crop_images(df, rgb_images):
    """Crop images for a series of data"""
    crops = {}
    geom = df.geometry.iloc[0]
    target_ind = df.target_ind.unique()[0]
   
    for tile in rgb_images:
        #find rgb data
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
        subject.metadata.update({"filename":filename})

    #Trigger upload
    subject.save()    
    
    return subject
    
def create_subject_set(everglades_watch, name="Nest detections 2.0"):
    subject_set = SubjectSet()
    subject_set.links.project = everglades_watch
    subject_set.display_name = name
    subject_set.save()

    return subject_set

def write_timestamp(image, text):
    text = text.replace("_projected","")
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
        #atleast three detections
        if group.shape[0] < 3:
            continue
        
        #Crop with date names as key
        site = group.Site.unique()[0]
        rgb_images = find_rgb_paths(site, rgb_pool)
        crops = crop_images(group, rgb_images=rgb_images)
        
        #save output
        dirname =  "{}/{}_{}".format(savedir,name,group["Site"].unique()[0])
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
    paths = [x for x in paths if not "Joule_05_05_2021" in x] # Joul 05_05_2021 is current not projected properly
    
    return paths

if __name__=="__main__":
    nest_shp = Path(detect_nests("/blue/ewhite/everglades/predictions/", savedir="../App/Zooniverse/data/"))
    processed_nests_shp = Path(process_nests(nest_shp, savedir="../App/Zooniverse/data/"))

    #Write nests into folders of clips
    rgb_pool = find_files()
    extract_nests(nest_shp, rgb_pool=rgb_pool, savedir="/orange/ewhite/everglades/nest_crops/", upload=False)

    # Zip the shapefiles for storage efficiency
    with ZipFile("../App/Zooniverse/data/nest_detections.zip", 'w', ZIP_DEFLATED) as zip:
        for ext in ['.cpg', '.dbf', '.prj', '.shp', '.shx']:
            focal_file = nest_shp.with_suffix(ext)
            file_name = focal_file.name
            zip.write(focal_file, arcname=file_name)
            os.remove(focal_file)

    with ZipFile("../App/Zooniverse/data/nest_detections_processed.zip", 'w', ZIP_DEFLATED) as zip:
        for ext in ['.cpg', '.dbf', '.prj', '.shp', '.shx']:
            focal_file = processed_nests_shp.with_suffix(ext)
            file_name = focal_file.name
            zip.write(focal_file, arcname=file_name)
            os.remove(focal_file)
