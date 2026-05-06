import os
import tools

configfile: "snakemake_config.yml"

# Check if the test environment variable exists
test_env_name = "TEST_ENV"
# Hardcode true for the moment while we're testing for safety.
test_env_set = True
working_dir = config["working_dir_test"] if test_env_set else config["working_dir"]

# Discover flights from raw data; year is the last '_'-delimited token in the folder name
RAW_DATA = glob_wildcards(f"{working_dir}/open_drone_map/RawData/SkyScoutFlights/{{site}}/{{flight}}")
FLIGHTS = RAW_DATA.flight
SITES = RAW_DATA.site
YEARS = [f.split('_')[-1] for f in FLIGHTS]


# Extract combinations of SITES and YEARS
site_year_combos = {*zip(SITES, YEARS)}
if site_year_combos:
    SITES_SY, YEARS_SY = list(zip(*site_year_combos))
else:
    SITES_SY, YEARS_SY = [], []


def flights_in_year_site(wildcards):
    basepath = f"{working_dir}/predictions"
    flights_in_year_site = []
    for site, year, flight in zip(SITES, YEARS, FLIGHTS):
        flight_path = os.path.join(basepath, year, site, f"{flight}_projected.shp")
        event = tools.get_event(flight_path)
        if site == wildcards.site and year == wildcards.year and event[0] == "primary":
            flights_in_year_site.append(flight_path)
    return flights_in_year_site


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


rule create_orthomosaics:
    input:
        raw_data_root=f"{working_dir}/open_drone_map/RawData/SkyScoutFlights/{{site}}/{{flight}}"
    output:
        orthomosaic=f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}.tif"
    log:
        f"{working_dir}/logs/create_orthomosaics/{{year}}/{{site}}/{{flight}}.log"
    conda: "envs/odm.yml"
    params:
        scratch_dir=f"{working_dir}/open_drone_map/ODM_Processed",
        slurm_extra="--gpus=1"
    wildcard_constraints:
        year=r"\d{4}"
    threads: 8
    resources:
        mem_mb=65536,
        runtime=720
    shell:
        "bash process_ortho.sh {input.raw_data_root} {output.orthomosaic} {params.scratch_dir} > {log} 2>&1"


rule project_mosaics:
    input:
        orthomosaic=f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}.tif"
    output:
        projected=f"{working_dir}/projected_mosaics/{{year}}/{{site}}/{{flight}}_projected.tif",
        webmercator=f"{working_dir}/projected_mosaics/webmercator/{{year}}/{{site}}/{{flight}}_projected.tif"
    log:
        f"{working_dir}/logs/project_mosaics/{{year}}/{{site}}/{{flight}}.log"
    conda: "envs/mbtiles.yml"
    threads: 1
    resources:
        mem_mb=32000,
        project_mosaic_slot=1
    shell:
        "python project_orthos.py {input.orthomosaic} > {log} 2>&1"


rule predict_birds:
    input:
        projected=f"{working_dir}/projected_mosaics/{{year}}/{{site}}/{{flight}}_projected.tif"
    output:
        f"{working_dir}/predictions/{{year}}/{{site}}/{{flight}}_projected.shp"
    log:
        f"{working_dir}/logs/predict_birds/{{year}}/{{site}}/{{flight}}.log"
    conda: "envs/predict.yml"
    threads: 1
    resources:
        gpu=1,
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
