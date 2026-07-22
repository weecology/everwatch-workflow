
## Shareable QGIS projects

The workflow also builds a per-site/year QGIS project so collaborators can inspect a
site's aligned orthomosaics and predictions in QGIS on their own machine. For each
site + year it writes, under the working dir:

```
qgis_projects/<year>/<site>/
    everwatch_<year>_<site>.qgz            
    everwatch_<year>_<site>_manifest.txt   # orthomosaics and predictions
    annotations/points.shp                 # and associated files
```

The project has an `Orthomosaics` group and a hidden `Predictions` group (the combined
site-year layer plus a `Per-flight` subgroup), with an editable `Annotations` point
layer at the top for marking features by hand. All datasources are stored using relative path so the bundle is portable, and the manifest lists the flight files the project references which can be used with `rsync --files-from`.

Build one site-year explicitly with:

```bash
snakemake --profile profiles/hipergator /blue/ewhite/everglades/qgis_projects/2026/Shamash/everwatch_2026_Shamash.qgz
```

### Sharing to another machine

Initial setup (once), for site `Shamash` in 2026:

```bash
# 1. Pull the flight data with the manifest
rsync -av --files-from=everwatch_2026_Shamash_manifest.txt hpc:/blue/ewhite/everglades/ ./everglades/
# 2. Copy the project folder once (gets the .qgz + empty annotations/points.shp)
rsync -av hpc:/blue/ewhite/everglades/qgis_projects/2026/Shamash/ ./everglades/qgis_projects/2026/Shamash/
# 3. Open ./everglades/qgis_projects/2026/Shamash/everwatch_2026_Shamash.qgz and start annotating
```

Ongoing updates (new flights added):

* Re-pull flights with the manifest (it excludes annotations, so edits survive).
* Re-pull just the refreshed `.qgz` file — **not** the `annotations/` folder, and never
  `rsync --delete` over the project folder. The reopened project shows all old + new
  predictions plus your accumulated annotations.

### Testing the QGIS step locally

The working dir and whether a run is a test (deployment skipped) are set by the active
profile: `profiles/hipergator` (production: real dir, deploys), `profiles/hipergator_test`
(test dir, no deploy), and `profiles/local` (no SLURM; supply the machine's `working_dir`
at runtime). `snakemake_config.yml` holds test-safe defaults.
The Snakefile exports the chosen dir as `EVERWATCH_WORKING_DIR` so standalone scripts
resolve the same dir as the rules.

To try `create_qgis_project.py` on a small pulled subset (one site, e.g. a 3-flight
sequence for a year):

```bash
LOCAL=~/everwatch_local  # your local working dir
YEAR=2026; SITE=Shamash

# 1. Predictions are tiny — pull the whole site/year dir (per-flight + combined + sidecars)
rsync -av hpc:/blue/ewhite/everglades/predictions/$YEAR/$SITE/ $LOCAL/predictions/$YEAR/$SITE/
# 2. Projected orthos (for display; larger) — pull the flights you want to see
rsync -av hpc:/blue/ewhite/everglades/projected_mosaics/$YEAR/$SITE/ $LOCAL/projected_mosaics/$YEAR/$SITE/

# 3. Scaffold orthomosaic placeholders so flight discovery finds them (no need to pull
#    the large original orthos), then generate:
bash tests/setup_local_qgis_test.sh $LOCAL
EVERWATCH_WORKING_DIR=$LOCAL python create_qgis_project.py $YEAR $SITE
```

Running needs PyQGIS — the conda `qgis` env (`mamba env create -f envs/qgis.yml`) or
your QGIS.app's bundled Python. Step 2 is optional: skip it to test project structure,
grouping, relative paths, and the manifest with the (tiny) predictions alone — the
ortho layers just show as unresolved until their tifs are present.