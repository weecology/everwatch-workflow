import csv
import datetime
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

# (site, year, flight) triple, as produced by discover_flights().
FlightCombination = tuple[str, str, str]


# Flight identifiers look like "<site>_<MM>_<DD>_<YYYY>" with an optional event
# suffix e.g. "<site>_<MM>_<DD>_<YYYY>_A".
_FLIGHT_RE = re.compile(
    r"_(?P<month>\d{1,2})_(?P<day>\d{1,2})_(?P<year>\d{4})(?:_(?P<event>[A-Za-z]+))?$"
)


class Flight(NamedTuple):
    """Parsed parts of a flight identifier; date fields kept as matched strings."""

    month: str
    day: str
    year: str
    event: str | None 


def _flight_stem(path: str) -> str:
    """basename of `path` without its extension or a trailing "_projected"."""
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem.endswith("_projected"):
        stem = stem[: -len("_projected")]
    return stem


def parse_flight(path: str) -> Flight:
    """Parse a flight name, directory, or prediction filename into its date + event.

    Handles bare names ("Rhea_West_05_08_2026"), suffixed names ("125_05_08_2026_A")
    and prediction files ("..._projected.shp"). Raises ValueError if no date is found.
    """
    match = _FLIGHT_RE.search(_flight_stem(path))
    if match is None:
        raise ValueError(f"Cannot parse flight date from {path!r}")
    return Flight(match["month"], match["day"], match["year"], match["event"])


def flight_year(path: str) -> str:
    """Four-digit acquisition year, as a string."""
    return parse_flight(path).year


def flight_date(path: str) -> datetime.date:
    """Acquisition date, e.g. for ordering flights chronologically."""
    f = parse_flight(path)
    return datetime.date(int(f.year), int(f.month), int(f.day))


def discover_flights(ortho_base: str, raw_base: str) -> tuple[set[FlightCombination], set[FlightCombination]]:
    """Find (site, year, flight) combinations from the orthomosaic and raw dirs.

    Returns (archive_combinations, raw_combinations):
      * archive: existing orthomosaics at <ortho_base>/<year>/<site>/<flight>.tif;
        year and site come from the directory layout.
      * raw: flight folders at <raw_base>/<site>/<flight>; the year is parsed from
        the flight name.
    """
    archive: set[FlightCombination] = set()
    for tif in sorted(Path(ortho_base).glob("*/*/*.tif")):
        if "_aligned" in tif.stem:
            continue
        archive.add((tif.parent.name, tif.parent.parent.name, tif.stem))

    raw: set[FlightCombination] = set()
    for flight_dir in sorted(p for p in Path(raw_base).glob("*/*") if p.is_dir()):
        raw.add((flight_dir.parent.name, flight_year(flight_dir.name), flight_dir.name))

    return archive, raw


def find_ppk_csv(root: str | os.PathLike) -> Path | None:
    """The WISPR PPK file ODM will be geotagged from, or None if there isn't one.

    A flight folder can hold more than one solution (e.g. CORS/ and VIRT/);
    prefer the virtual base station one.
    """
    found = sorted(Path(root).rglob("exif_image_list.csv"))
    virtual = [path for path in found if "virt" in str(path.relative_to(root)).lower()]
    candidates = virtual or found
    return candidates[0] if candidates else None


def load_exclusions(path: str | os.PathLike) -> set[FlightCombination]:
    """Load flight exclusions from a CSV

    The CSV should contain a header row "year,site,flight" and then one row per flight to exclude.

    The flight column is the date part of the flight name, with its event suffix if
    it has one, e.g. "05_08_2026_B".
    """
    path = Path(path)
    if not path.exists():
        return set()

    exclusions: set[FlightCombination] = set()
    with path.open(newline="") as handle:
        for lineno, row in enumerate(csv.reader(handle), start=1):
            fields = [value.strip() for value in row]
            if not any(fields) or fields[0].startswith("#"):
                continue
            if len(fields) != 3:
                raise ValueError(f"{path}:{lineno}: expected 3 columns (year,site,flight), got {row!r}")
            year, site, flight = fields
            if [value.casefold() for value in fields] == ["year", "site", "flight"]:
                continue
            exclusions.add((site, year, flight))
    return exclusions


EXCLUDE_HEADER = ("# Flights listed here are skipped by the workflow; the flight column is the\n"
                  "# flight name without the site prefix, e.g. 05_08_2026_B.\n"
                  "year,site,flight\n")


def add_exclusion(path: str | os.PathLike, combination: FlightCombination,
                  reason: str | None = None) -> bool:
    """Add a flight to the exclude file, writing the file if it isn't there yet.

    Returns False if the flight was already listed.
    """
    path = Path(path)
    site, year, flight = _exclusion_key(combination)
    if (site, year, flight) in load_exclusions(path):
        return False

    existing = path.read_text() if path.exists() else EXCLUDE_HEADER
    if not existing.endswith("\n"):
        existing += "\n"
    if reason:
        existing += f"# {reason}\n"
    path.write_text(f"{existing}{year},{site},{flight}\n")
    return True


def _exclusion_key(combination: FlightCombination) -> FlightCombination:
    """A discovered flight written the way the exclude file writes it."""
    site, year, flight = combination
    try:
        return (site, year, get_date(flight) + get_event(flight)[1])
    except ValueError:
        # No date in the name, so no exclude row can name it.
        return combination


@dataclass(frozen=True)
class FlightIndex:
    """Flights discovered under a working dir.

    `sites`/`years`/`flights` are aligned (one entry per flight) for use with
    Snakemake's expand(..., zip, ...);
    
    `sites_sy`/`years_sy` are unique site/year pairs.

    `excluded` holds the flights that were found but dropped via exclude.txt
    """

    all_combinations: list[FlightCombination]
    build: set[FlightCombination]
    sites: list[str]
    years: list[str]
    flights: list[str]
    sites_sy: list[str]
    years_sy: list[str]
    prev_flight: dict[str, str | None]
    excluded: list[FlightCombination]

    def previous_flight(self, flight: str) -> str | None:
        """The chronologically preceding flight at the same site/year, or None."""
        return self.prev_flight.get(flight)

    def has_previous(self, flight: str | None) -> bool:
        """True if `flight` has a predecessor (i.e. not the first of its season)."""
        if flight is None:
            return False
        return self.prev_flight.get(flight) is not None

    def needs_odm(self, site: str, year: str, flight: str) -> bool:
        """True if this flight needs ODM (raw imagery with no existing orthomosaic)."""
        return (site, year, flight) in self.build

    def primary_flights(self, site: str, year: str) -> list[str]:
        """Flight names for the given site/year whose event is the primary survey."""
        return [
            flight
            for s, y, flight in self.all_combinations
            if s == site and y == year and get_event(flight)[0] == "primary"
        ]


def build_flight_index(ortho_base: str, raw_base: str, exclusions: set[FlightCombination] = frozenset()) -> FlightIndex:
    """Discover flights from the orthomosaic and raw dirs, derive combos + ordering.

    Flights listed in `exclusions` are not processed.
    """
    archive, raw = discover_flights(ortho_base, raw_base)
    excluded = {c for c in archive | raw if _exclusion_key(c) in exclusions}
    all_combinations = sorted((archive | raw) - excluded)
    build = raw - archive - excluded

    sites = [site for site, _, _ in all_combinations]
    years = [year for _, year, _ in all_combinations]
    flights = [flight for _, _, flight in all_combinations]

    site_year = sorted({(site, year) for site, year, _ in all_combinations})
    sites_sy = [site for site, _ in site_year]
    years_sy = [year for _, year in site_year]

    # Within each (site, year), order flights by date and map each to its predecessor.
    by_site_year: dict[tuple[str, str], list[str]] = {}
    for site, year, flight in all_combinations:
        by_site_year.setdefault((site, year), []).append(flight)
    prev_flight: dict[str, str | None] = {}
    for ordered in by_site_year.values():
        ordered.sort(key=flight_date)
        for i, flight in enumerate(ordered):
            prev_flight[flight] = ordered[i - 1] if i > 0 else None

    return FlightIndex(
        all_combinations=all_combinations,
        build=build,
        sites=sites,
        years=years,
        flights=flights,
        sites_sy=sites_sy,
        years_sy=years_sy,
        prev_flight=prev_flight,
        excluded=sorted(excluded),
    )


def get_date(x: str) -> str:
    """Date portion of a flight filename as "MM_DD_YYYY"."""
    f = parse_flight(x)
    return f"{f.month}_{f.day}_{f.year}"


def get_event(path: str) -> tuple[str, str]:
    """
    Determines the event for a given flight.

    Flight names are "<site>_<month>_<day>_<year>", with an optional
    suffix "<site>_<month>_<day>_<year>_<event>".
    
    Returns "primary" for "A"/"a"/"primary/None"; otherwise the upper-cased event.
    The second element is the filename suffix ("" or "_<EVENT>").
    """
    try:
        event = parse_flight(path).event
    except ValueError:
        return ("primary", "")
    if event is None:
        return ("primary", "")
    event = event.upper()
    if event in {"A", "PRIMARY"}:
        return ("primary", "_" + event)
    return (event, "_" + event)


def get_site(path: str) -> str:
    """Site name parsed from a "<site>_<MM>_<DD>_<YYYY>..._projected" filename."""
    name = os.path.basename(path)
    match = re.match(r"(\w+)_\d+_\d+_\d+.*_projected", name)
    if match is None:
        raise ValueError(f"Cannot parse site from {path!r}")
    return match.group(1)


def get_working_dir() -> str:
    # The Snakefile exports EVERWATCH_WORKING_DIR from
    # config["working_dir"] (set by the active profile) so standalone scripts resolve
    # the same dir as the rules.
    override = os.environ.get("EVERWATCH_WORKING_DIR")
    if override:
        return override
    return "/blue/ewhite/everglades"
