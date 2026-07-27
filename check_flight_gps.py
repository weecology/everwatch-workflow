#!/usr/bin/env python3
"""Check that a flight's images are geo-referenced, before ODM is run on them.

An image is considered geo-referenced if it has GPS EXIF tags, or if it appears in the WISPR PPK
file (exif_image_list.csv) that becomes ODM's geo.txt. Either source alone is enough:
ODM takes coordinates from geo.txt where it has them and falls back to each image's own
EXIF. Flights usually start with a frame or two shot before the receiver gets a fix, so
the check passes when "most" of the images are geo-referenced. Only top-level JPEGs are
looked at, which is what create_ortho.sh copies for ODM. By default, 90% is the minimum
acceptable fraction.

Usage:
    python check_flight_gps.py FLIGHT_DIR [--fraction 0.9]

Exit status is 0 if the flight can go to ODM, 1 if it should not.
"""

import argparse
import csv
import sys
from pathlib import Path

from PIL import ExifTags, Image

import tools

JPEG_SUFFIXES = {".jpg", ".jpeg"}


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


def ppk_images(csv_path: Path) -> set[str]:
    """Image filenames listed in a WISPR PPK file."""
    with csv_path.open(newline="") as handle:
        return {row["image_name"] for row in csv.DictReader(handle)}


def can_georeference(flight_dir: Path, fraction: float = 0.9) -> bool:
    """True if enough of the flight's images are geo-referenced for ODM to use.

    Prints where the coordinates came from and which images have none.
    """
    images = flight_jpegs(flight_dir)
    if not images:
        print(f"{flight_dir.name}: no images found", file=sys.stderr)
        return False

    csv_path = tools.find_ppk_csv(flight_dir)
    ppk = ppk_images(csv_path) if csv_path else set()

    from_ppk = [p for p in images if p.name in ppk]
    exif_only = [p for p in images if p.name not in ppk and has_exif_gps(p)]
    georeferenced = set(from_ppk) | set(exif_only)
    missing = [p for p in images if p not in georeferenced]

    where = csv_path.parent.relative_to(flight_dir) if csv_path else "no PPK file"
    print(f"{flight_dir.name}: {len(images)} images | PPK {len(from_ppk)} ({where}) | "
          f"EXIF only {len(exif_only)} | no geo-reference {len(missing)}")
    for path in missing:
        print(f"    no geo-reference: {path.name}")

    if not georeferenced or len(georeferenced) / len(images) < fraction:
        print(f"{flight_dir.name}: only {len(georeferenced)}/{len(images)} images are "
              f"geo-referenced, need {fraction:.0%}", file=sys.stderr)
        return False
    return True


def exclude_flight(exclude_file: Path, flight_dir: Path) -> None:
    """Add the flight to the exclude file so later runs skip it."""
    site, flight = flight_dir.parent.name, flight_dir.name
    try:
        combination = (site, tools.flight_year(flight), flight)
    except ValueError:
        print(f"Cannot parse a year from {flight}, so it can't be excluded", file=sys.stderr)
        return
    if tools.add_exclusion(exclude_file, combination,
                           reason=f"{flight}: too few geo-referenced images"):
        print(f"Added {flight} to {exclude_file}; later runs will skip it")
    else:
        print(f"{flight} is already listed in {exclude_file}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("flight_dir", type=Path, help="Folder holding the flight's images.")
    ap.add_argument("--fraction", type=float, default=0.9,
                    help="Fraction of images that must be geo-referenced (default 0.9).")
    ap.add_argument("--exclude-file", type=Path,
                    help="Add the flight to this exclude file if the check fails.")
    args = ap.parse_args(argv)

    if not args.flight_dir.is_dir():
        sys.exit(f"Not a directory: {args.flight_dir}")

    if can_georeference(args.flight_dir, args.fraction):
        return 0
    if args.exclude_file:
        exclude_flight(args.exclude_file, args.flight_dir)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
