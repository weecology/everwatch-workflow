#!/usr/bin/env python
"""Build a shareable per-site/year QGIS project + an rsync manifest.

For one site in one year this writes a QGIS project
(``qgis_projects/<year>/<site>/everwatch_<year>_<site>.qgz``).

The layer tree has an ``Orthomosaics`` group and a ``Predictions`` group,
with the ``Predictions`` group hidden by default.  A single editable
``Annotations`` point layer is added for user annotations e.g. nest
labels.

All datasources are stored as *relative* paths so the project is portable.  A
manifest of every referenced flight file (relative to the working dir) is written
alongside for ``rsync --files-from`` so a user can pull exactly the needed
files while preserving the directory tree.

Sharing workflow
----------------
Layout produced under the working dir::

    qgis_projects/<year>/<site>/
        everwatch_<year>_<site>.qgz            # regenerated each run; safe to re-pull
        everwatch_<year>_<site>_manifest.txt   # flight files only; NO annotations
        annotations/points.shp (+sides)        # seeded empty once; reviewer-owned
    projected_mosaics/<year>/<site>/...
    predictions/<year>/<site>/...

Initial setup (once):
    1. On HPC: ``snakemake --use-conda .../qgis_projects/2023/Joule/everwatch_2023_Joule.qgz``
    2. ``rsync -av --files-from=everwatch_2023_Joule_manifest.txt hpc:<working_dir>/ ./dest/``
    3. Copy the project folder once (gets the .qgz + empty annotations/points.shp):
       ``rsync -av hpc:<working_dir>/qgis_projects/2023/Joule/ ./dest/qgis_projects/2023/Joule/``
    4. Open ``dest/qgis_projects/2023/Joule/everwatch_2023_Joule.qgz`` and start annotating.

Ongoing updates (new flights added):
    * Re-pull flights with the manifest.
    * Re-pull just the refreshed ``.qgz`` file
"""

import argparse
import os
import sys
from collections.abc import Iterable
from typing import NamedTuple

import yaml

import tools

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsField,
    QgsFields,
    QgsLayerTreeGroup,
    QgsMapLayer,
    QgsProject,
    QgsRasterLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

PROJECT_CRS = "EPSG:32617"
SHAPEFILE_FILES = (".shp", ".shx", ".dbf", ".prj", ".cpg")

# Schema for the point annotation layer
ANNOTATION_FIELDS = (
    ("id", QVariant.Int),
    ("site", QVariant.String),
    ("label", QVariant.String),
    ("notes", QVariant.String),
)


def sidecars(shp_path: str) -> list[str]:
    """All ESRI sidecar paths for a shapefile (whether or not they exist yet)."""
    stem = os.path.splitext(shp_path)[0]
    return [stem + ext for ext in SHAPEFILE_FILES]


def flights_for_site(index: tools.FlightIndex, year: str, site: str) -> list[str]:
    """Flights for the given site/year, ordered chronologically."""
    flights = [f for s, y, f in index.all_combinations if y == year and s == site]
    flights.sort(key=tools.flight_date)
    return flights


def create_annotation_layer(points_shp: str) -> None:
    """Create an empty point shapefile for annotations, only if it is absent.
    """
    if os.path.exists(points_shp):
        return
    os.makedirs(os.path.dirname(points_shp), exist_ok=True)

    fields = QgsFields()
    for name, qtype in ANNOTATION_FIELDS:
        fields.append(QgsField(name, qtype))

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "ESRI Shapefile"
    writer = QgsVectorFileWriter.create(
        points_shp,
        fields,
        QgsWkbTypes.Point,
        QgsCoordinateReferenceSystem(PROJECT_CRS),
        QgsCoordinateTransformContext(),
        options,
    )
    if writer.hasError() != QgsVectorFileWriter.NoError:
        raise RuntimeError(
            f"Failed to create annotation layer {points_shp}: {writer.errorMessage()}"
        )
    del writer  # flush to disk


def _add_layer(
    project: QgsProject,
    group: QgsLayerTreeGroup,
    path: str,
    name: str,
    provider: str,
) -> QgsMapLayer:
    """Register a layer and attach it to a layer tree group. Does not check
    if the file exists.
    """
    if provider == "gdal":
        layer = QgsRasterLayer(path, name)
    else:
        layer = QgsVectorLayer(path, name, provider)
    if not layer.isValid():
        print(f"WARNING: layer not valid, adding anyway: {path}", file=sys.stderr)
    project.addMapLayer(layer, False)
    group.addLayer(layer)
    return layer


def write_manifest(manifest_path: str, entries: Iterable[str]) -> None:
    """Creates a manifest file listing the given entries, one per line.

    Can be used with: ``rsync --files-from``
    """
    seen = set()
    lines = []
    for entry in entries:
        if entry not in seen:
            seen.add(entry)
            lines.append(entry)
    with open(manifest_path, "w") as fp:
        fp.write("\n".join(lines) + "\n")


class ProjectPaths(NamedTuple):
    """Output paths for one site-year project, all under ``project_dir``."""

    project_dir: str
    qgz: str
    manifest: str
    points_shp: str


def project_paths(working_dir: str, year: str, site: str) -> ProjectPaths:
    """Resolve the output paths for a site-year project."""
    project_dir = os.path.join(working_dir, "qgis_projects", year, site)
    stem = f"everwatch_{year}_{site}"
    return ProjectPaths(
        project_dir=project_dir,
        qgz=os.path.join(project_dir, f"{stem}.qgz"),
        manifest=os.path.join(project_dir, f"{stem}_manifest.txt"),
        points_shp=os.path.join(project_dir, "annotations", "points.shp"),
    )


def load_flight_index(working_dir: str) -> tools.FlightIndex:
    """Discover flights under ``working_dir`` using the configured base dirs."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "snakemake_config.yml")) as fp:
        smcfg = yaml.safe_load(fp)
    ortho_base = os.path.join(working_dir, smcfg["orthomosaic_dir"])
    raw_base = os.path.join(working_dir, smcfg["raw_flight_dir"])
    return tools.build_flight_index(ortho_base, raw_base)


def add_orthomosaics(
    project: QgsProject,
    root: QgsLayerTreeGroup,
    working_dir: str,
    year: str,
    site: str,
    flights: list[str],
) -> list[str]:
    """Add the projected orthos as an ``Orthomosaics`` group. Returns manifest entries."""
    group = root.addGroup("Orthomosaics")
    manifest: list[str] = []
    for flight in flights:
        tif = os.path.join(
            working_dir, "projected_mosaics", year, site, f"{flight}_projected.tif",
        )
        _add_layer(project, group, tif, flight, "gdal")
        manifest.append(os.path.relpath(tif, working_dir))
    return manifest


def add_predictions(
    project: QgsProject,
    root: QgsLayerTreeGroup,
    working_dir: str,
    year: str,
    site: str,
    flights: list[str],
) -> list[str]:
    """Add a ``Predictions`` group (combined layer + ``Per-flight`` subgroup), hidden
    by default. Returns manifest entries.
    """
    group = root.addGroup("Predictions")
    manifest: list[str] = []

    combined = os.path.join(
        working_dir, "predictions", year, site, f"{site}_{year}_combined.shp",
    )
    _add_layer(project, group, combined, f"{site}_{year}_combined", "ogr")
    manifest.extend(os.path.relpath(s, working_dir) for s in sidecars(combined))

    perflight_grp = group.addGroup("Per-flight")
    for flight in flights:
        shp = os.path.join(
            working_dir, "predictions", year, site, f"{flight}_projected.shp",
        )
        _add_layer(project, perflight_grp, shp, flight, "ogr")
        manifest.extend(os.path.relpath(s, working_dir) for s in sidecars(shp))

    group.setItemVisibilityChecked(False)  # hide predictions by default
    return manifest


def add_annotations(
    project: QgsProject, root: QgsLayerTreeGroup, points_shp: str, layer_name="Annotations"
) -> None:
    """Add an annotation point layer"""
    annotations = QgsVectorLayer(points_shp, layer_name, "ogr")
    if not annotations.isValid():
        print(f"WARNING: annotation layer not valid: {points_shp}", file=sys.stderr)
    project.addMapLayer(annotations, False)
    root.insertLayer(0, annotations)


def use_relative_paths(project: QgsProject) -> None:
    """Store datasources relative to the project file for portability"""
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    project.writeEntryBool("Paths", "/Absolute", False)


def build(year: str, site: str) -> None:
    working_dir = tools.get_working_dir()
    index = load_flight_index(working_dir)
    flights = flights_for_site(index, year, site)
    paths = project_paths(working_dir, year, site)
    os.makedirs(paths.project_dir, exist_ok=True)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qgs = QgsApplication([], False)
    QgsApplication.setPrefixPath(os.environ.get("CONDA_PREFIX", "/usr"), True)
    qgs.initQgis()
    try:
        create_annotation_layer(paths.points_shp)

        project = QgsProject.instance()
        project.clear()
        project.setFileName(paths.qgz)
        project.setCrs(QgsCoordinateReferenceSystem(PROJECT_CRS))
        root = project.layerTreeRoot()

        # Flight paths relative to the working dir, for the manifest.
        manifest: list[str] = []
        manifest += add_orthomosaics(project, root, working_dir, year, site, flights)
        manifest += add_predictions(project, root, working_dir, year, site, flights)
        add_annotations(project, root, paths.points_shp)

        use_relative_paths(project)
        if not project.write(paths.qgz):
            raise RuntimeError(f"Failed to write project {paths.qgz}")

        # The user also needs the project file itself.
        manifest.append(os.path.relpath(paths.qgz, working_dir))
        write_manifest(paths.manifest, manifest)
        print(f"Wrote {paths.qgz}")
        print(f"Wrote {paths.manifest}")
    finally:
        qgs.exitQgis()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build a shareable per-site/year QGIS project + an rsync manifest.",
    )
    parser.add_argument("year", help="acquisition year, e.g. 2026")
    parser.add_argument("site", help="site name, e.g. Shamash")
    args = parser.parse_args(argv)
    build(args.year, args.site)


if __name__ == "__main__":
    main()
