# Everwatch Workflow
<!-- badges: start -->
<!-- badges: end -->

Workflow for processing UAS (i.e., drone) imagery into data on the location, species, and nesting of individual birds in the Everglades. 

## Environment

The primary environment for this workflow can be built with conda or mamba (faster) from the included environment.yml file:

```sh
mamba env create -f=environment.yml
```

The environment is setup to work with NVIDIA GPUs since that is what we use on our HPC.

## Syncing Dropbox to HiperGator

Data is synced nightly to the HPC using cron and a set of rclone commands of the form:

```sh
rclone sync everglades2023:"Wading Bird 2023/Deliverables/" /blue/ewhite/everglades/2023
```

## Snakemake Workflow

Once imagery arrives on the HPC as an orthomosaic, a nightly Snakemake workflow runs all of the steps for processing imagery, projecting geospatial data (for both analysis and web visualization), predicting birds, predicting nests, and pushing imagery to mapbox for web visualization.

Snakemake processes any new data or data that has been updated while ignoring data that has already been processed. So a new when a new orthomosaic is synced that imagery will be processed and any combined files that depend on that imagery regenerated.

The general command for running the snakemake workflow is:

```bash
snakemake --printshellcmds --keep-going --cores 10 --resources gpu=2 --rerun-incomplete --latency-wait 10 --use-conda
```

`--cores` is the number of cores and `--resources gpu=` is the number of gpus to be used.

The workflow currently does the following:
1. Projects all orthomosaics in `/blue/ewhite/everglades/orthomosaics` using `project_orthos.py`
2. Predicts the location and species ID of all birds in each orthomosaic using `predict.py`
3. Combines all of the predictions into single shapefiles for each site-year combination (`combine_birds_site_year.py`) and then a single combined zipped shapefile (`combine_bird_predictions.py`).
4. Detects nests based on three or more occurrences of a bird detection at the same location during a single year (`nest_detection.py`), processes this data into a useful format for visualization and analysis (`process_nests.py`), and combines them into a single zipped shapefile (`combine_nests.py`).
5. Processes imagery into mbtiles files for web visualization (`mbtile.py`) and uploads these files to mapbox using the API (`upload_mapbox.py`).

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

The output shapefiles for (4) contain the predicted nest polygon, site, date and a unique identifier.
```
>>> gdf[["Site","Date","target_ind"]].head()
          Site        Date  target_ind
0        Aerie  04_27_2020         880
1        Aerie  04_27_2020         880
2  CypressCity  03_11_2020           7
3  CypressCity  04_29_2020           7
4  CypressCity  04_01_2020           8
```

## Logs

The logs are located in `/blue/ewhite/everglades/EvergladesTools/logs`
Checkout the current cronjob in `/blue/ewhite/everglades/EvergladesTools/everglades_workflow.sh`
