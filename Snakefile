import os
import re
import tools
from datetime import date as _date
from pathlib import Path

configfile: "snakemake_config.yml"

# Set test environment variable for tools.get_working_dir()
os.environ["TEST_ENV"] = "1"

# Hardcode true for the moment while we're testing for safety.
test_env_set = True
working_dir = config["working_dir_test"]


_ortho_base = Path(working_dir) / "orthomosaics"
_raw_base = Path(working_dir) / "open_drone_map/RawData/SkyScoutFlights"

SITES = []
FLIGHTS = []
YEARS = []

# Discover existing orthomosaics and prefer to not regenerate if possible
for _tif in sorted(_ortho_base.glob("*/*/*.tif")):
    if "_aligned" in _tif.stem:
        continue
    SITES.append(_tif.parent.name)
    FLIGHTS.append(_tif.stem)
    YEARS.append(_tif.parent.parent.name)

EXISTING_ORTHO_FLIGHTS = set(FLIGHTS)

# Raw flights are built only when no ortho exists for them yet.
CREATE_FLIGHTS = set()
for _dir in sorted(p for p in _raw_base.glob("*/*") if p.is_dir()):
    _flight = _dir.name
    if _flight in EXISTING_ORTHO_FLIGHTS:
        continue
    SITES.append(_dir.parent.name)
    FLIGHTS.append(_flight)
    YEARS.append(_flight.split("_")[-1])
    CREATE_FLIGHTS.add(_flight)

# Extract combinations of SITES and YEARS
site_year_combos = {*zip(SITES, YEARS)}
if site_year_combos:
    SITES_SY, YEARS_SY = list(zip(*site_year_combos))
else:
    SITES_SY, YEARS_SY = [], []

# Build per-site-year chronological lookup: map each flight to its predecessor
def _parse_flight_date(flight_name):
    parts = flight_name.split("_")
    try:
        mm, dd, yyyy = int(parts[-3]), int(parts[-2]), int(parts[-1])
    except (ValueError, IndexError) as e:
        raise ValueError(f"Cannot parse date from flight name {flight_name!r} (parts={parts}): {e}")
    return _date(yyyy, mm, dd)

_site_year_flights: dict[tuple[str, str], list[str]] = {}
for _s, _y, _f in zip(SITES, YEARS, FLIGHTS):
    _site_year_flights.setdefault((_s, _y), []).append(_f)
for _key in _site_year_flights:
    _site_year_flights[_key].sort(key=_parse_flight_date)

_prev_flight: dict[str, str | None] = {}
for (_s, _y), _ordered in _site_year_flights.items():
    for _i, _f in enumerate(_ordered):
        _prev_flight[_f] = _ordered[_i - 1] if _i > 0 else None


def _get_reference_ortho(wildcards):
    """Returns the previous aligned flight for the given input, used as reference for alignment."""
    prev = _prev_flight[wildcards.flight]
    if _prev_flight.get(prev) is not None:
        return f"{working_dir}/orthomosaics/{wildcards.year}/{wildcards.site}/{prev}_aligned.tif"
    return f"{working_dir}/orthomosaics/{wildcards.year}/{wildcards.site}/{prev}.tif"

def _has_previous_flight(wildcards):
    """Checks if the previous flight exists, e.g. this is the first flight of the season for that site"""
    return _prev_flight.get(wildcards.flight) is not None


def flights_in_year_site(wildcards):
    """Discover flights by site and year"""
    basepath = f"{working_dir}/predictions"
    flights_in_year_site = []
    for site, year, flight in zip(SITES, YEARS, FLIGHTS):
        flight_path = os.path.join(basepath, year, site, f"{flight}_projected.shp")
        event = tools.get_event(flight_path)
        if site == wildcards.site and year == wildcards.year and event[0] == "primary":
            flights_in_year_site.append(flight_path)
    return flights_in_year_site


wildcard_constraints:
    year=r"\d{4}",
    flight=r".*(?<!_aligned)"

ruleorder: existing_orthomosaic > create_orthomosaics


rule all:
    input:
        f"{working_dir}/everwatch-workflow/App/Zooniverse/data/PredictedBirds.zip",
        f"{working_dir}/everwatch-workflow/App/Zooniverse/data/nest_detections_processed.zip",
        f"{working_dir}/everwatch-workflow/App/Zooniverse/data/forecast_web_updated.txt",
        expand(f"{working_dir}/predictions/{{year}}/{{site}}/{{flight}}_projected.shp",
               zip, site=SITES, year=YEARS, flight=FLIGHTS),
        expand(f"{working_dir}/processed_nests/{{year}}/{{site}}/{{site}}_{{year}}_processed_nests.shp",
               zip, site=SITES, year=YEARS),
        expand(f"{working_dir}/mapbox/last_uploaded/{{year}}/{{site}}/{{flight}}.mbtiles",
               zip, site=SITES, year=YEARS, flight=FLIGHTS)


rule existing_orthomosaic:
    """No-op for pre-existing orthomosaics"""
    output:
        orthomosaic=f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}.tif"
    wildcard_constraints:
        flight="|".join(sorted(re.escape(f) for f in EXISTING_ORTHO_FLIGHTS)) or "(?!)"
    shell:
        "test -f {output.orthomosaic}"


rule create_orthomosaics:
    input:
        raw_data_root=f"{working_dir}/open_drone_map/RawData/SkyScoutFlights/{{site}}/{{flight}}"
    output:
        orthomosaic=f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}.tif"
    wildcard_constraints:
        flight="|".join(sorted(re.escape(f) for f in CREATE_FLIGHTS)) or "(?!)"
    log:
        f"{working_dir}/logs/create_orthomosaics/{{year}}/{{site}}/{{flight}}.log"
    conda: "envs/odm.yml"
    params:
        scratch_dir=f"{working_dir}/open_drone_map/ODM_Processed",
        slurm_extra="--gpus=1"
    threads: 8
    resources:
        mem_mb=65536,
        runtime=720
    shell:
        "bash process_ortho.sh {input.raw_data_root} {output.orthomosaic} {params.scratch_dir} > {log} 2>&1"


rule align_mosaics:
    input:
        orthomosaic=f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}.tif",
        reference=_get_reference_ortho,
    output:
        aligned=f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}_aligned.tif",
    log:
        f"{working_dir}/logs/align_mosaics/{{year}}/{{site}}/{{flight}}.log"
    params:
        align_dir=f"{working_dir}/orthomosaics/{{year}}/{{site}}/align/{{flight}}",
    conda: "envs/odm.yml"
    threads: 12
    resources:
        mem_mb=32000,
        runtime=10
    shell:
        """
        exec > {log:q} 2>&1
        orthoalign \
            {input.reference:q} \
            {input.orthomosaic:q} \
            --out-dir {params.align_dir:q} \
            --transform homography \
            --workers {threads} \
            --cleanup
        mv {params.align_dir:q}/{wildcards.flight}_aligned_homography.tif \
            {output.aligned:q}
        """


rule project_mosaics:
    input:
        orthomosaic=branch(
            _has_previous_flight,
            then=f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}_aligned.tif",
            otherwise=f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}.tif",
        )
    output:
        projected=f"{working_dir}/projected_mosaics/{{year}}/{{site}}/{{flight}}_projected.tif"
    log:
        f"{working_dir}/logs/project_mosaics/{{year}}/{{site}}/{{flight}}.log"
    conda: "envs/mbtiles.yml"
    threads: 12
    resources:
        mem_mb=32000,
        project_mosaic_slot=1
    shell:
        "bash project_ortho.sh {input.orthomosaic:q} {output.projected:q} 32617 -wo NUM_THREADS={threads} > {log:q} 2>&1"


rule project_mosaics_webmercator:
    input:
        orthomosaic=branch(
            _has_previous_flight,
            then=f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}_aligned.tif",
            otherwise=f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}.tif",
        )
    output:
        webmercator=f"{working_dir}/projected_mosaics/webmercator/{{year}}/{{site}}/{{flight}}_projected.tif"
    log:
        f"{working_dir}/logs/project_mosaics_webmercator/{{year}}/{{site}}/{{flight}}.log"
    conda: "envs/mbtiles.yml"
    threads: 12
    resources:
        mem_mb=32000,
        project_mosaic_slot=1
    shell:
        "bash project_ortho.sh {input.orthomosaic:q} {output.webmercator:q} 3857 -wo NUM_THREADS={threads} > {log:q} 2>&1"


rule predict_birds:
    input:
        projected=f"{working_dir}/projected_mosaics/{{year}}/{{site}}/{{flight}}_projected.tif"
    output:
        f"{working_dir}/predictions/{{year}}/{{site}}/{{flight}}_projected.shp"
    log:
        f"{working_dir}/logs/predict_birds/{{year}}/{{site}}/{{flight}}.log"
    conda: "envs/predict.yml"
    params:
        slurm_extra="--gpus=1"
    threads: 1
    resources:
        mem_mb=40000,
        predict_birds_slot=1
    shell:
        "python predict.py {input.projected} > {log} 2>&1"


rule combine_birds_site_year:
    input:
        flights_in_year_site
    output:
        f"{working_dir}/predictions/{{year}}/{{site}}/{{site}}_{{year}}_combined.shp"
    log:
        f"{working_dir}/logs/combine_birds_site_year/{{year}}/{{site}}.log"
    conda: "envs/everwatch.yml"
    threads: 1
    resources:
        mem_mb=8000
    shell:
        "python combine_birds_site_year.py {input} > {log} 2>&1"


rule combine_predicted_birds:
    input:
        expand(f"{working_dir}/predictions/{{year}}/{{site}}/{{site}}_{{year}}_combined.shp",
               zip, site=SITES_SY, year=YEARS_SY)
    output:
        f"{working_dir}/everwatch-workflow/App/Zooniverse/data/PredictedBirds.zip"
    log:
        f"{working_dir}/logs/combine_predicted_birds.log"
    conda: "envs/everwatch.yml"
    threads: 1
    resources:
        mem_mb=8000
    shell:
        "python combine_bird_predictions.py {input} > {log} 2>&1"


rule detect_nests:
    input:
        f"{working_dir}/predictions/{{year}}/{{site}}/{{site}}_{{year}}_combined.shp"
    output:
        f"{working_dir}/detected_nests/{{year}}/{{site}}/{{site}}_{{year}}_detected_nests.shp"
    log:
        f"{working_dir}/logs/detect_nests/{{year}}/{{site}}.log"
    conda: "envs/everwatch.yml"
    threads: 1
    resources:
        mem_mb=8000
    shell:
        "python nest_detection.py {input} > {log} 2>&1"


rule process_nests:
    input:
        f"{working_dir}/detected_nests/{{year}}/{{site}}/{{site}}_{{year}}_detected_nests.shp"
    output:
        f"{working_dir}/processed_nests/{{year}}/{{site}}/{{site}}_{{year}}_processed_nests.shp"
    log:
        f"{working_dir}/logs/process_nests/{{year}}/{{site}}.log"
    conda: "envs/everwatch.yml"
    threads: 1
    resources:
        mem_mb=8000
    shell:
        "python process_nests.py {input} > {log} 2>&1"


rule combine_nests:
    input:
        expand(f"{working_dir}/processed_nests/{{year}}/{{site}}/{{site}}_{{year}}_processed_nests.shp",
               zip, site=SITES_SY, year=YEARS_SY)
    output:
        f"{working_dir}/everwatch-workflow/App/Zooniverse/data/nest_detections_processed.zip"
    log:
        f"{working_dir}/logs/combine_nests.log"
    conda: "envs/everwatch.yml"
    threads: 1
    resources:
        mem_mb=8000
    shell:
        "python combine_nests.py {input} > {log} 2>&1"


rule create_mbtile:
    input:
        f"{working_dir}/projected_mosaics/webmercator/{{year}}/{{site}}/{{flight}}_projected.tif"
    output:
        f"{working_dir}/mapbox/{{year}}/{{site}}/{{flight}}.mbtiles"
    log:
        f"{working_dir}/logs/create_mbtile/{{year}}/{{site}}/{{flight}}.log"
    params:
        mapbox_param=config["mapbox-param"]
    conda: "envs/mbtiles.yml"
    threads: 1
    resources:
        mem_mb=32000
    shell:
        "python mbtile.py {input} {params.mapbox_param} > {log} 2>&1"


rule upload_mapbox:
    input:
        f"{working_dir}/mapbox/{{year}}/{{site}}/{{flight}}.mbtiles"
    output:
        f"{working_dir}/mapbox/last_uploaded/{{year}}/{{site}}/{{flight}}.mbtiles"
    log:
        f"{working_dir}/logs/upload_mapbox/{{year}}/{{site}}/{{flight}}.log"
    conda: "envs/mbtiles.yml"
    threads: 1
    resources:
        mem_mb=4000
    shell:
        """
        python upload_mapbox.py {input} > {log} 2>&1
        touch {output}
        """


rule update_everwatch_predictions:
    input:
        f"{working_dir}/everwatch-workflow/App/Zooniverse/data/PredictedBirds.zip"
    output:
        f"{working_dir}/everwatch-workflow/App/Zooniverse/data/forecast_web_updated.txt"
    log:
        f"{working_dir}/logs/update_everwatch_predictions.log"
    conda: "envs/everwatch.yml"
    threads: 1
    resources:
        mem_mb=4000
    shell:
        """
        bash archive_predictions.sh > {log} 2>&1
        touch {output}
        """
