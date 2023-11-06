# EvergladesWadingBird Data
<!-- badges: start -->
<!-- badges: end -->

Project Organization
------------

    ├── LICENSE
    ├── README.md          <- The top-level README for developers using this project.
    ├── App                <- Shiny App for visualizing results from Zooniverse and predictions 
    |-- Zooniverse         <- bird detection model training, bird-bird-bird prediction and parsing Zooniverse annotations
        |-- SLURM            <- SLURM scripts for submitting jobs on Hipergator
        |-- species_model    <- Multi-class species model
        |-- aggregate.py     <- Main script for downloading and cleaning Zooniverse annotatiosn
        |-- extract.py       <- Download images that match annotations from Zooniverse
        |-- cron.txt         <- Cron job to run a model and sync the dropbox
        |-- manifest.py      <- upload images to Zooniverse
        |-- nest_aggregate.py <- Download and clean nest label series from Zooniverse
        |-- nest_detection.py <- Generate predicted nests using Bird-Bird-Bird
        |-- predict.py       <- Predict bird locations
        |-- start_cluster.py <- Useful dask utilities for parallel data processing
        |-- tile_raster.py   <- Split a large orthomosaic into smaller tiles
        |-- upload_mapbox.py <- Upload data to mapbox for visualization server
--------

# Zooniverse Authentication

The tokens.py file needs to be placed (outside of git) in the /Zooniverse folder to authenticate. This file was provided on the everglades slack channel within Weecology organization.

# Set Up

Accessing Mapbox requires an [API access token](https://www.mapbox.com/studio/account/tokens/). The access token can be set using `.Renviron` in either the working directory or home directory or by exporting it as an environment variable `$ export MAPBOX_ACCESS_TOKEN=MY_TOKEN`


# Download and clean Zooniverse annotations

To download the image crops and corresponding annotations
```
python aggregate.py
```
This saves the raw zooniverse data to 
```
/App/Zooniverse/data/everglades-watch-classifications.csv
```

followed by

```
python extract.py
```

which saves image crops and annotation shapefiles to

```
/orange/ewhite/everglades/Zooniverse/parsed_images/
```

# Bird-Bird-Bird Workflow

## Environment

Conda or mamba (faster)
```
mamba env create -f=environment.yml
```
The environment can be sensitive to the new CUDA version. Its often useful to first install torch and torch vision from -c pytorch and then install the rest of the environment.

## Syncing Dropbox to HiperGator

```
rclone sync everglades2021:"Wading Bird 2021/Deliverables/" /orange/ewhite/everglades/2021
```

## HiperGator Logs

The logs are located in `/blue/ewhite/everglades/EvergladesTools/logs`
Checkout the current cronjob in `/blue/ewhite/everglades/EvergladesTools/everglades_workflow.sh`

## Snakemake Workflow

There is a Snakemake workflow that runs most of (soon all of) the steps for predicting birds, predicting nests, and pushing imagery to mapbox.

The run the snakemake workflow from a node with the appropriate resources run:

```bash
snakemake --printshellcmds --keep-going --cores 10 --resources gpu=2
```

Replace `10` with the number of cores to run on and `2` with the number of gpus available.

The workflow currently does the following:
1. Projects all orthomosaics in `/blue/ewhite/everglades/orthomosaics` using `project_orthos.py`
2. Predicts the location and species ID of all birds in each orthomosaic using `predict.py`
3. Combines all of the predictions into a single shape file using `combine_bird_predictions.py`

The output shapefiles from (2) and (3) contain the predicted polygon, confidence score, site and event date.

```
>>> import geopandas as gpd
>>> gdf[["score","site","event"]]
          score     site       event
0      0.246132   Jerrod  03_24_2020
1      0.349666   Jerrod  03_24_2020
...         ...      ...         ...
14033  0.270656  Yonteau  04_27_2020
14034  0.237832  Yonteau  04_27_2020
```

We are currently adding the following to the workflow:
1. Predicting the location of nests in each orthomosaic
2. Combining all of the nest predictions into a single shape file
3. Projecting orthomosaics into the mapbox projection
4. Creating mbtiles files for mapbox
5. Pushing those mbtiles files to mapbox

The existing code for steps (1) and (2) follow the following steps:

```
python Zooniverse/nest_detection.py
```

This will save nest series images to 

```
/orange/ewhite/everglades/nest_crops/
```
and a aggregate shapefile at 

```
/orange/ewhite/everglades/nest_crops/nest_detections.shp
```

The shapefile contains the predicted nest polygon, site, date and a unique identifier.
```
>>> gdf[["Site","Date","target_ind"]].head()
          Site        Date  target_ind
0        Aerie  04_27_2020         880
1        Aerie  04_27_2020         880
2  CypressCity  03_11_2020           7
3  CypressCity  04_29_2020           7
4  CypressCity  04_01_2020           8
```

The existing code steps (3) - (5) is in `upload_mapbox.py`

### Force re-upload to mapbox

If you are updating existing imagery you will need to force it to be updated.
In `Zooniverse/snakemake_config.yml` change the value for `mapbox-param` to `"--force-upload"`.
This will overwrite the current imagery on mapbox for all orthos touched by the snakemake run.

# Shiny App

## Dependencies

```r
install.packages(c('shiny', 'shinythemes', 'shinyWidgets', 'leaflet', 'sf'))
```

## Run the app

```r
shiny::runApp('./App/Zooniverse')
```

## Viewing new data in the Shiny App

Sometimes when we are doing work on the image manipulation or models it is useful to preview new data in Shiny app.
This involves two components:

1. New data on the location of birds
2. New imagery which is served via mapbox

### New data on birds

This component can be explored without impacting the overall workflow by following these steps:

1. Generate new bird predictions
2. Don't commit these data to the primary source (https://github.com/weecology/EvergladesTools/tree/main/App/Zooniverse/data)
3. Replace the relevant files, typically `PredictedBirds.zip` or `nest_detections_processed.zip`, in your local repository in the `App/Zooniverse/data` directory
4. Load the App as described above

### Newly processed imagery

Exploring differently processed imagery requires hosting that imagery on Mapbox.
Currently the only approach supported for viewing in the Shiny App is replacing the production imagery.

1. Add the new orthomosaics to the HiPerGator
2. Project the orthomosaics using `snakemake -R project_mosaics --keep-going --cores 10` where the number after jobs is the number of workers. Scaling will be near linear with the number of workers. This should automatically reproject any orthomosaics that have been updated
3. Add imagery to mapbox
   1. If the imagery is for a new location/date you push all of the new imagery to mapbox using `snakemake -R upload_mapbox --keep-going --cores 10`
   2. If you are updating existing imagery you will need to force it to be updated. For each file you want to update run `python upload_mapbox.py /path/to/file --force-upload`. This will overwrite the current file on mapbox.
4. Load the app as described above. The app loads the imagery from mapbox. If it isn't updated it may be that mapbox is still processing the updated files. 