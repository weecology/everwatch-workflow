
## Shareable QGIS projects

The workflow also builds a per-site/year QGIS project so collaborators can inspect a
site's aligned orthomosaics and predictions in QGIS on their own machine. Every project
shares one flat `qgis_projects/` root, so all sites/years open from a single folder:

```
qgis_projects/
    everwatch_<year>_<site>.qgz
    everwatch_<year>_<site>_manifest.txt                     # orthomosaics and predictions
    orthomosaics/<year>/<site>/*.tif                         # symlinks into projected_mosaics/
    predictions/<year>/<site>/*.shp (+ sidecars)             # symlinks into predictions/
    annotations/everwatch_<year>_<site>_points.shp (+ sidecars)
```

The layer tree, top to bottom, is an editable `Annotations` point layer for marking
features by hand, a hidden `Predictions` group (the combined site-year layer plus a
`Per-flight` subgroup) and an `Orthomosaics` group.

The orthos/predictions are symlinked into subfolders during Snake make, with relative paths. The manifest lists those symlinked files
for `rsync --files-from`; pull with `rsync -L` so the real files are copied next to the project.

Build one site-year explicitly with e.g.:

```bash
snakemake --profile profiles/hipergator /blue/ewhite/everglades/qgis_projects/everwatch_2026_Shamash.qgz
```

### Sharing to another machine

Initial setup, for `Shamash` in 2026:

```bash
# 1. Pull the flight data with the manifest. -L follows the symlinks and copies the real
#    orthos/predictions into ./everglades/qgis_projects/{orthomosaics,predictions}/
rsync -avL --files-from=everwatch_2026_Shamash_manifest.txt hpc:/blue/ewhite/everglades/ ./everglades/
# 2. Pull the empty annotations once
rsync -av hpc:/blue/ewhite/everglades/qgis_projects/annotations/ ./everglades/qgis_projects/annotations/
```

To update:

* Re-pull flights with the manifest (`rsync -avL`)
* Re-pull just the refreshed `.qgz`