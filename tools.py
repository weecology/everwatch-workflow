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


@dataclass(frozen=True)
class FlightIndex:
    """Flights discovered under a working dir.

    `sites`/`years`/`flights` are aligned (one entry per flight) for use with
    Snakemake's expand(..., zip, ...);
    
    `sites_sy`/`years_sy` are unique site/year pairs.
    """

    all_combinations: list[FlightCombination]
    build: set[FlightCombination]
    sites: list[str]
    years: list[str]
    flights: list[str]
    sites_sy: list[str]
    years_sy: list[str]
    prev_flight: dict[str, str | None]

    def previous_flight(self, flight: str) -> str | None:
        """The chronologically preceding flight at the same site/year, or None."""
        return self.prev_flight.get(flight)

    def has_previous(self, flight: str | None) -> bool:
        """True if `flight` has a predecessor (i.e. not the first of its season)."""
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


def build_flight_index(ortho_base: str, raw_base: str) -> FlightIndex:
    """Discover flights from the orthomosaic and raw dirs, derive combos + ordering."""
    archive, raw = discover_flights(ortho_base, raw_base)
    all_combinations = sorted(archive | raw)
    build = raw - archive

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
