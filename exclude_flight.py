#!/usr/bin/env python3
"""Add a flight to the exclude file so later workflow runs skip it.

Used by check_flight_gps.py before ODM runs, and by create_ortho.sh when ODM fails for
a reason that a rerun will not fix, such as too few usable images.

Usage:
    python exclude_flight.py FLIGHT_DIR --exclude-file PATH [--reason TEXT]

FLIGHT_DIR is <...>/<site>/<flight>; the site and flight names come from the path.

"""

import argparse
import sys
from pathlib import Path
import logging
import tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def exclude_flight(exclude_file: Path, flight_dir: Path, reason: str | None = None) -> bool:
    """Add the flight to the exclude file. Returns True if a row was written."""
    site, flight = flight_dir.parent.name, flight_dir.name
    try:
        combination = (site, tools.flight_year(flight), flight)
    except ValueError:
        logger.error(f"Cannot parse a year from {flight}, so it can't be excluded")
        return False
    if tools.add_exclusion(exclude_file, combination, reason=reason):
        logger.info(f"Added {flight} to {exclude_file}; later runs will skip it")
        return True
    logger.info(f"{flight} is already listed in {exclude_file}")
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("flight_dir", type=Path, help="Folder holding the flight's images.")
    ap.add_argument("--exclude-file", type=Path, required=True,
                    help="Exclude file to add the flight to.")
    ap.add_argument("--reason", help="Comment written above the row.")
    args = ap.parse_args(argv)

    exclude_flight(args.exclude_file, args.flight_dir, args.reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
