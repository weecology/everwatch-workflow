#!/usr/bin/env python3
"""Check that a flight's images are geo-referenced, before ODM is run on them.

An image is considered geo-referenced if it has GPS EXIF tags, or if it appears in the WISPR PPK
file (exif_image_list.csv) that becomes ODM's geo.txt. Either source alone is enough:
ODM takes coordinates from geo.txt where it has them and falls back to each image's own
EXIF. Flights usually start with a frame or two shot before the receiver gets a fix, so
the check passes when "most" of the images are geo-referenced. Only top-level JPEGs are
looked at, which is what create_ortho.sh copies for ODM. By default, 90% is the minimum
acceptable fraction.

With --image-list, the names of the geo-referenced images are written to a file that
create_ortho.sh uses as a manifest. Images with no determinable coordinates are dropped.

Usage:
    python check_flight_gps.py FLIGHT_DIR [--fraction 0.9] [--image-list PATH]

Exit status is 0 if the flight can go to ODM, 1 if it should not.
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import NamedTuple

from PIL import ExifTags, Image

import tools
from exclude_flight import exclude_flight

JPEG_SUFFIXES = {".jpg", ".jpeg"}


class FlightImages(NamedTuple):
    """A flight's images, split by whether coordinates were found for them."""

    from_ppk: list[Path]
    exif_only: list[Path]
    missing: list[Path]
    ppk_csv: Path | None = None

    @property
    def georeferenced(self) -> list[Path]:
        """Images ODM will have a position for, in flight order."""
        return sorted(self.from_ppk + self.exif_only)

    @property
    def total(self) -> int:
        return len(self.from_ppk) + len(self.exif_only) + len(self.missing)


def flight_jpegs(flight_dir: Path) -> list[Path]:
    """Top-level JPEGs in a flight folder, sorted."""
    return sorted(
        p for p in flight_dir.iterdir()
        if p.is_file() and p.suffix.lower() in JPEG_SUFFIXES
    )


def has_exif_gps(path: Path) -> bool:
    """True if the image carries GPS coordinates. False if it doesn't, or can't be read."""
    try:
        gps = Image.open(path).getexif().get_ifd(ExifTags.IFD.GPSInfo)
    except Exception:
        return False
    # GPSLatitude = tag 2, GPSLongitude = tag 4 in the GPS IFD.
    return bool(gps.get(2)) and bool(gps.get(4))


def has_ppk_coordinates(row: dict[str, str]) -> bool:
    """True if a PPK row holds a latitude and longitude that read as numbers."""
    try:
        float(row["latitude"])
        float(row["longitude"])
    except (KeyError, TypeError, ValueError):
        return False
    return True


def ppk_images(csv_path: Path) -> set[str]:
    """Image filenames that a WISPR PPK file gives coordinates for."""
    with csv_path.open(newline="") as handle:
        return {row["image_name"] for row in csv.DictReader(handle) if has_ppk_coordinates(row)}


def sort_images(flight_dir: Path) -> FlightImages:
    """Group a flight's images by where their coordinates come from, if anywhere."""
    images = flight_jpegs(flight_dir)
    csv_path = tools.find_ppk_csv(flight_dir)
    ppk = ppk_images(csv_path) if csv_path else set()

    from_ppk = [p for p in images if p.name in ppk]
    exif_only = [p for p in images if p.name not in ppk and has_exif_gps(p)]
    georeferenced = set(from_ppk) | set(exif_only)
    missing = [p for p in images if p not in georeferenced]
    return FlightImages(from_ppk, exif_only, missing, csv_path)


def write_image_list(path: Path, images: list[Path]) -> None:
    """Write image names, one per line, for `rsync --files-from`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{image.name}\n" for image in images))


def can_georeference(flight_dir: Path, fraction: float = 0.9,
                     image_list: Path | None = None) -> bool:
    """True if enough of the flight's images are geo-referenced for ODM to use.

    Prints where the coordinates came from and which images have none. On success,
    writes the geo-referenced image names to `image_list` if one was given.
    """
    images = sort_images(flight_dir)
    if not images.total:
        print(f"{flight_dir.name}: no images found", file=sys.stderr)
        return False

    where = images.ppk_csv.parent.relative_to(flight_dir) if images.ppk_csv else "no PPK file"
    print(f"{flight_dir.name}: {images.total} images | PPK {len(images.from_ppk)} ({where}) | "
          f"EXIF only {len(images.exif_only)} | no geo-reference {len(images.missing)}")
    for path in images.missing:
        print(f"    no geo-reference, will not be sent to ODM: {path.name}")

    georeferenced = images.georeferenced
    if not georeferenced or len(georeferenced) / images.total < fraction:
        print(f"{flight_dir.name}: only {len(georeferenced)}/{images.total} images are "
              f"geo-referenced, need {fraction:.0%}", file=sys.stderr)
        return False

    if image_list is not None:
        write_image_list(image_list, georeferenced)
        print(f"{flight_dir.name}: listed {len(georeferenced)} images for ODM in {image_list}")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("flight_dir", type=Path, help="Folder holding the flight's images.")
    ap.add_argument("--fraction", type=float, default=0.9,
                    help="Fraction of images that must be geo-referenced (default 0.9).")
    ap.add_argument("--exclude-file", type=Path,
                    help="Add the flight to this exclude file if the check fails.")
    ap.add_argument("--image-list", type=Path,
                    help="Write the geo-referenced image names here, for ODM to be run on.")
    args = ap.parse_args(argv)

    if not args.flight_dir.is_dir():
        sys.exit(f"Not a directory: {args.flight_dir}")

    if can_georeference(args.flight_dir, args.fraction, args.image_list):
        return 0
    if args.exclude_file:
        exclude_flight(args.exclude_file, args.flight_dir,
                       reason=f"{args.flight_dir.name}: too few geo-referenced images")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
