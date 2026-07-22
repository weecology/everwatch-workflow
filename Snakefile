import os
import tools

configfile: "snakemake_config.yml"

# `working_dir` and `test` come from the active profile (see profiles/*). Export the
# working dir so standalone scripts (via tools.get_working_dir) resolve the same dir as
# the rules do.
working_dir = config["working_dir"]
os.environ["EVERWATCH_WORKING_DIR"] = working_dir

# `test` gates deployment: prod publishes predictions, a test run only smoke-tests the
# publish path (see `rule all` and the two deploy rules below). Consumed at DAG build.
test = str(config.get("test", True)).strip().lower() not in ("false", "0", "no", "")


# Discover flights and derive all combos + chronological ordering. Base dirs come from config.
ortho_base = f"{working_dir}/{config['orthomosaic_dir']}"
raw_base = f"{working_dir}/{config['raw_flight_dir']}"
flight_index = tools.build_flight_index(ortho_base, raw_base)
SITES, YEARS, FLIGHTS = flight_index.sites, flight_index.years, flight_index.flights
SITES_SY, YEARS_SY = flight_index.sites_sy, flight_index.years_sy


def _get_reference_ortho(wildcards):
    """Previous flight's orthomosaic, used as the alignment reference."""
    prev = flight_index.previous_flight(wildcards.flight)
    suffix = "_aligned" if flight_index.has_previous(prev) else ""
    return f"{working_dir}/orthomosaics_work/{wildcards.year}/{wildcards.site}/{prev}{suffix}.tif"


def _has_previous_flight(wildcards):
    """False if this is the first flight of the season for that site."""
    return flight_index.has_previous(wildcards.flight)


def _will_build_orthomosaic(wildcards):
    return flight_index.needs_odm(wildcards.site, wildcards.year, wildcards.flight)


def flights_in_year_site(wildcards):
    """Primary-event prediction shapefiles for the given site/year."""
    return [
        f"{working_dir}/predictions/{wildcards.year}/{wildcards.site}/{flight}_projected.shp"
        for flight in flight_index.primary_flights(wildcards.site, wildcards.year)
    ]


def qgis_inputs_for_site(wildcards):
    """Every ortho + prediction the site/year QGIS project references.

    Referenced to projected images so it regenerates when flights change or are added.
    """
    flights = [
        f for s, y, f in flight_index.all_combinations
        if y == wildcards.year and s == wildcards.site
    ]
    inputs = []
    for flight in flights:
        inputs.append(f"{working_dir}/projected_mosaics/{wildcards.year}/{wildcards.site}/{flight}_projected.tif")
        inputs.append(f"{working_dir}/predictions/{wildcards.year}/{wildcards.site}/{flight}_projected.shp")
    inputs.append(f"{working_dir}/predictions/{wildcards.year}/{wildcards.site}/{wildcards.site}_{wildcards.year}_combined.shp")
    return inputs


wildcard_constraints:
    year=r"\d{4}",
    flight=r".*(?<!_aligned)"


rule all:
    input:
        f"{working_dir}/everwatch-workflow/App/Zooniverse/data/PredictedBirds.zip",
        f"{working_dir}/everwatch-workflow/App/Zooniverse/data/nest_detections_processed.zip",
        # Deploy: prod publishes predictions; a test run only smoke-tests the publish
        # path. Selecting one target here means only that deploy rule joins the DAG.
        (f"{working_dir}/everwatch-workflow/App/Zooniverse/data/forecast_web_updated.txt"
         if not test else
         f"{working_dir}/everwatch-workflow/App/Zooniverse/data/forecast_web_dryrun.txt"),
        expand(f"{working_dir}/predictions/{{year}}/{{site}}/{{flight}}_projected.shp",
               zip, site=SITES, year=YEARS, flight=FLIGHTS),
        expand(f"{working_dir}/processed_nests/{{year}}/{{site}}/{{site}}_{{year}}_processed_nests.shp",
               zip, site=SITES, year=YEARS),
        expand(f"{working_dir}/mapbox/last_uploaded/{{year}}/{{site}}/{{flight}}.mbtiles",
               zip, site=SITES, year=YEARS, flight=FLIGHTS),
        expand(f"{working_dir}/qgis_projects/{{year}}/{{site}}/everwatch_{{year}}_{{site}}.qgz",
               zip, site=SITES_SY, year=YEARS_SY)


# We create symlinks to a working directory that can be used for subsequent steps.
# This rule will  call a create_ortho script which should be idempotent.
# If the output exists, we'll skip ODM. Since this doesn't require a big resouce
#request, we only  request a large machine. This redirection is necessary so that
# only a single rule that outputs an orthomosaic. If you split this section
# into two parts (e.g. skip_creation/create), it causes problems with the output
# becoming stale between runs (as the output now points to a different rule) and 
# snakemake will delete the file.
rule create_orthomosaics:
    output:
        orthomosaic=f"{working_dir}/orthomosaics_work/{{year}}/{{site}}/{{flight}}.tif"
    log:
        f"{working_dir}/logs/create_orthomosaics/{{year}}/{{site}}/{{flight}}.log"
    conda: "envs/odm.yml"
    params:
        working_dir=working_dir,
        scratch_dir=f"{working_dir}/open_drone_map/ODM_Processed",
        slurm_extra=lambda wildcards: "--gpus=1" if _will_build_orthomosaic(wildcards) else ""
    threads: lambda wildcards: 8 if _will_build_orthomosaic(wildcards) else 1
    resources:
        mem_mb=lambda wildcards: 65536 if _will_build_orthomosaic(wildcards) else 2048,
        runtime=lambda wildcards: 720 if _will_build_orthomosaic(wildcards) else 10
    shell:
        "bash create_ortho.sh {wildcards.site:q} {wildcards.year:q} {wildcards.flight:q} {params.working_dir:q} {params.scratch_dir:q} > {log:q} 2>&1"


rule align_mosaics:
    input:
        orthomosaic=f"{working_dir}/orthomosaics_work/{{year}}/{{site}}/{{flight}}.tif",
        reference=_get_reference_ortho,
    output:
        aligned=f"{working_dir}/orthomosaics_work/{{year}}/{{site}}/{{flight}}_aligned.tif",
    log:
        f"{working_dir}/logs/align_mosaics/{{year}}/{{site}}/{{flight}}.log"
    params:
        align_dir=f"{working_dir}/orthomosaics_work/{{year}}/{{site}}/align/{{flight}}",
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
            then=f"{working_dir}/orthomosaics_work/{{year}}/{{site}}/{{flight}}_aligned.tif",
            otherwise=f"{working_dir}/orthomosaics_work/{{year}}/{{site}}/{{flight}}.tif",
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
            then=f"{working_dir}/orthomosaics_work/{{year}}/{{site}}/{{flight}}_aligned.tif",
            otherwise=f"{working_dir}/orthomosaics_work/{{year}}/{{site}}/{{flight}}.tif",
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


# Deploy the finished predictions to the public everwatch-predictions repo. Only one of
# the two rules below joins the DAG, selected by `test` in `rule all`.
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
        bash archive_predictions.sh deploy > {log} 2>&1
        touch {output}
        """


# Nightly smoke test of the publish path (token, remote, push) without touching main.
rule deploy_dryrun:
    input:
        f"{working_dir}/everwatch-workflow/App/Zooniverse/data/PredictedBirds.zip"
    output:
        f"{working_dir}/everwatch-workflow/App/Zooniverse/data/forecast_web_dryrun.txt"
    log:
        f"{working_dir}/logs/deploy_dryrun.log"
    conda: "envs/everwatch.yml"
    threads: 1
    resources:
        mem_mb=4000
    shell:
        """
        bash archive_predictions.sh dryrun > {log} 2>&1
        touch {output}
        """


# Create a shareable QGIS project with relative paths, plus an rsync manifest of the referenced files.
rule create_qgis_project:
    input:
        qgis_inputs_for_site
    output:
        qgz=f"{working_dir}/qgis_projects/{{year}}/{{site}}/everwatch_{{year}}_{{site}}.qgz",
        manifest=f"{working_dir}/qgis_projects/{{year}}/{{site}}/everwatch_{{year}}_{{site}}_manifest.txt"
    log:
        f"{working_dir}/logs/create_qgis_project/{{year}}/{{site}}.log"
    conda: "envs/qgis.yml"
    threads: 1
    resources:
        mem_mb=2000
    shell:
        "python create_qgis_project.py {wildcards.year} {wildcards.site} > {log:q} 2>&1"
