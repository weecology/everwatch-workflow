#!/usr/bin/env python
"""Build a shareable per-site/year QGIS project + an rsync manifest.

For one site + year this writes a QGIS project
(``qgis_projects/everwatch_<year>_<site>.qgz``).  All projects share a
``qgis_projects/`` root relative to orthos etc.

The layer tree contains an editable ``Annotations`` point layer (for
nest labels etc.), a ``Predictions`` group, then an ``Orthomosaics`` group.

During Snakemake, orthos and predictions a project references are *symlinked* into subfolders
beside the ``.qgz`` (``orthomosaics/<year>/<site>/``, ``predictions/<year>/<site>/``).
Datasources are stored *relative* so the bundle is portable; a
manifest of the symlinked files (relative to the working dir) is written for
``rsync --files-from``.  Because the entries are symlinks, pull with ``rsync -L`` to pull
the real files instead of the symlinks.

Sharing workflow
----------------
Layout produced under the working dir::

    qgis_projects/
        everwatch_<year>_<site>.qgz               # regenerated each run; safe to re-pull
        everwatch_<year>_<site>_manifest.txt      # symlinked flight files; NO annotations
        orthomosaics/<year>/<site>/*.tif          # symlinks -> ../projected_mosaics/...
        predictions/<year>/<site>/*.shp (+sides)  # symlinks -> ../predictions/...
        annotations/everwatch_<year>_<site>_points.shp (+sides)  # created empty once; owned by the reviewer

Initial setup (once), for site Joule in 2023:
    1. On hpg: ``snakemake --use-conda .../qgis_projects/everwatch_2023_Joule.qgz``
    2. Pull the referenced files:
       ``rsync -avL --files-from=everwatch_2023_Joule_manifest.txt hpg:<working_dir>/ ./dest/``
    3. Pull the empty annotations once:
       ``rsync -av hpg:<working_dir>/qgis_projects/annotations/ ./dest/qgis_projects/annotations/``
    4. Open ``dest/qgis_projects/everwatch_2023_Joule.qgz`` and start annotating.

To update:
    * Re-pull flights with the manifest (``rsync -avL``); it excludes annotations.
    * Re-pull just the refreshed ``.qgz`` file.
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
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsField,
    QgsFields,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsReferencedRectangle,
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


def symlink_into(link_dir: str, src: str) -> str:
    """Create/refresh a relative symlink to ``src`` inside ``link_dir``.

    ``link_dir`` must already exist. Returns the link path.
    """
    link = os.path.join(link_dir, os.path.basename(src))
    target = os.path.relpath(src, link_dir)
    if os.path.islink(link):
        if os.readlink(link) == target:
            return link
        os.remove(link)
    elif os.path.exists(link):
        os.remove(link)
    os.symlink(target, link)
    return link


def link_shapefile(link_dir: str, shp: str) -> tuple[str, list[str]]:
    """Symlink an existing shapefile's parts (``.shp`` + sidecars) into
    ``link_dir``. Returns the ``.shp`` link path and every link created.
    """
    links = [symlink_into(link_dir, src) for src in sidecars(shp) if os.path.exists(src)]
    shp_link = os.path.join(link_dir, os.path.basename(shp))
    return shp_link, links


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
) -> QgsLayerTreeLayer:
    """Register a layer and attach it to a layer tree group. Does not check
    if the file exists.
    
    Returns the layer-tree node.
    """
    if provider == "gdal":
        layer = QgsRasterLayer(path, name)
    else:
        layer = QgsVectorLayer(path, name, provider)
    if not layer.isValid():
        print(f"WARNING: layer not valid, adding anyway: {path}", file=sys.stderr)
    project.addMapLayer(layer, False)
    return group.addLayer(layer)


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
    """Output paths for one site-year project.

    Projects share the same root: the ``.qgz`` and its manifest sit directly in the root,
    while orthos, predictions and annotations live in subfolders alongside it.
    """

    root_dir: str
    qgz: str
    manifest: str
    points_shp: str
    ortho_dir: str
    pred_dir: str


def project_paths(working_dir: str, year: str, site: str) -> ProjectPaths:
    """Resolve the output paths for a site-year project."""
    root_dir = os.path.join(working_dir, "qgis_projects")
    stem = f"everwatch_{year}_{site}"
    return ProjectPaths(
        root_dir=root_dir,
        qgz=os.path.join(root_dir, f"{stem}.qgz"),
        manifest=os.path.join(root_dir, f"{stem}_manifest.txt"),
        points_shp=os.path.join(root_dir, "annotations", f"{stem}_points.shp"),
        ortho_dir=os.path.join(root_dir, "orthomosaics", year, site),
        pred_dir=os.path.join(root_dir, "predictions", year, site),
    )


def load_flight_index(working_dir: str) -> tools.FlightIndex:
    """Discover flights under ``working_dir`` using the configured base dirs."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "snakemake_config.yml")) as fp:
        smcfg = yaml.safe_load(fp)
    ortho_base = os.path.join(working_dir, smcfg["orthomosaic_dir"])
    raw_bases = tools.resolve_raw_bases(working_dir, smcfg["raw_flight_dir"])
    exclude_file = os.path.join(here, smcfg["exclude_file"])
    return tools.build_flight_index(ortho_base, raw_bases, tools.load_exclusions(exclude_file))


def add_orthomosaics(
    project: QgsProject,
    root: QgsLayerTreeGroup,
    working_dir: str,
    ortho_dir: str,
    year: str,
    site: str,
    flights: list[str],
) -> list[str]:
    """Add the projected orthos as an ``Orthomosaics`` group, symlinked into
    ``ortho_dir`` beside the project. Returns manifest entries.
    """
    group = root.addGroup("Orthomosaics")
    os.makedirs(ortho_dir, exist_ok=True)
    manifest: list[str] = []
    # flights are chronological, show in reverse order
    earliest = flights[0] if flights else None
    for flight in reversed(flights):
        tif = os.path.join(
            working_dir, "projected_mosaics", year, site, f"{flight}_projected.tif",
        )
        # Only symlink (and list in the manifest) orthos that exist, mirroring
        # link_shapefile, so a missing ortho doesn't leave a dangling symlink that
        # `rsync -L` would choke on. The layer is still added (shows unresolved).
        link = os.path.join(ortho_dir, os.path.basename(tif))
        if os.path.exists(tif):
            symlink_into(ortho_dir, tif)
            manifest.append(os.path.relpath(link, working_dir))
        node = _add_layer(project, group, link, flight, "gdal")
        node.setItemVisibilityChecked(flight == earliest)
    return manifest


def add_predictions(
    project: QgsProject,
    root: QgsLayerTreeGroup,
    working_dir: str,
    pred_dir: str,
    year: str,
    site: str,
    flights: list[str],
) -> list[str]:
    """Add a ``Predictions`` group (combined layer + ``Per-flight`` subgroup), hidden
    by default, symlinked into ``pred_dir`` beside the project. Returns manifest entries.
    """
    group = root.addGroup("Predictions")
    os.makedirs(pred_dir, exist_ok=True)
    manifest: list[str] = []

    combined = os.path.join(
        working_dir, "predictions", year, site, f"{site}_{year}_combined.shp",
    )
    shp_link, links = link_shapefile(pred_dir, combined)
    _add_layer(project, group, shp_link, f"{site}_{year}_combined", "ogr")
    manifest.extend(os.path.relpath(link, working_dir) for link in links)

    perflight_grp = group.addGroup("Per-flight")
    for flight in reversed(flights):
        shp = os.path.join(
            working_dir, "predictions", year, site, f"{flight}_projected.shp",
        )
        shp_link, links = link_shapefile(pred_dir, shp)
        _add_layer(project, perflight_grp, shp_link, flight, "ogr")
        manifest.extend(os.path.relpath(link, working_dir) for link in links)

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


def set_initial_extent(project: QgsProject) -> None:
    """Set project extent to the combined extent of all raster layers.
    """
    extent = QgsRectangle()
    extent.setNull()
    crs = project.crs()
    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsRasterLayer) or not layer.isValid():
            continue
        layer_extent = layer.extent()
        if layer.crs() != crs:
            transform = QgsCoordinateTransform(layer.crs(), crs, project.transformContext())
            layer_extent = transform.transformBoundingBox(layer_extent)
        extent.combineExtentWith(layer_extent)
    if extent.isNull() or extent.isEmpty():
        return
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(extent, crs))


def build(year: str, site: str) -> None:
    working_dir = tools.get_working_dir()
    index = load_flight_index(working_dir)
    flights = flights_for_site(index, year, site)
    paths = project_paths(working_dir, year, site)
    os.makedirs(paths.root_dir, exist_ok=True)

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
        manifest += add_predictions(
            project, root, working_dir, paths.pred_dir, year, site, flights
        )
        manifest += add_orthomosaics(
            project, root, working_dir, paths.ortho_dir, year, site, flights
        )
        add_annotations(project, root, paths.points_shp)

        set_initial_extent(project)
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
