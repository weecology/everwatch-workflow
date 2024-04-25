import glob
import os
import tools

configfile: "/blue/ewhite/everglades/EvergladesTools/snakemake_config.yml"

# Check if the test environment variable exists
test_env_name = "TEST_ENV"
test_env_set = os.environ.get(test_env_name)
working_dir = "/blue/ewhite/everglades_test" if test_env_set else "/blue/ewhite/everglades"

# Define wildcards for orthomosaics
ORTHOMOSAICS = glob_wildcards(f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}.tif")
FLIGHTS = ORTHOMOSAICS.flight
SITES = ORTHOMOSAICS.site
YEARS = ORTHOMOSAICS.year

# Extract combinations of SITES and YEARS
site_year_combos = {*zip(SITES, YEARS)}
SITES_SY, YEARS_SY = list(zip(*site_year_combos))

def flights_in_year_site(wildcards):
    basepath = f"{working_dir}/predictions"
    flights_in_year_site = []
    for site, year, flight in zip(SITES, YEARS, FLIGHTS):
        flight_path = os.path.join(basepath, year, site, f"{flight}_projected.shp")
        # Assuming there is a tools.get_event function
        event = tools.get_event(flight_path)
        if site == wildcards.site and year == wildcards.year and event[0] == "primary":
            flights_in_year_site.append(flight_path)
    return flights_in_year_site

rule all:
    input:
        f"{working_dir}/EvergladesTools/App/Zooniverse/data/PredictedBirds.zip",
        f"{working_dir}/EvergladesTools/App/Zooniverse/data/nest_detections_processed.zip",
        expand(f"{working_dir}/predictions/{{year}}/{{site}}/{{flight}}_projected.shp",
               zip, site=SITES, year=YEARS, flight=FLIGHTS),
        expand(f"{working_dir}/processed_nests/{{year}}/{{site}}/{{site}}_{{year}}_processed_nests.shp",
               zip, site=SITES, year=YEARS),
        expand(f"{working_dir}/mapbox/last_uploaded/{{year}}/{{site}}/{{flight}}.mbtiles",
               zip, site=SITES, year=YEARS, flight=FLIGHTS)


rule project_mosaics:
    input:
        orthomosaic=f"{working_dir}/orthomosaics/{{year}}/{{site}}/{{flight}}.tif"
    output:
        projected=f"{working_dir}/projected_mosaics/{{year}}/{{site}}/{{flight}}_projected.tif",
        webmercator=f"{working_dir}/projected_mosaics/webmercator/{{year}}/{{site}}/{{flight}}_projected.tif"
    conda:
        "EvergladesTools"
    shell:
        "python project_orthos.py {input.orthomosaic}"

rule predict_birds:
    input:
        projected=f"{working_dir}/projected_mosaics/{{year}}/{{site}}/{{flight}}_projected.tif"
    output:
        f"{working_dir}/predictions/{{year}}/{{site}}/{{flight}}_projected.shp"
    conda:
        "EvergladesTools"
    resources:
        gpu=1
    shell:
        "python predict.py {input.projected}"

rule combine_birds_site_year:
    input:
        flights_in_year_site
    output:
        f"{working_dir}/predictions/{{year}}/{{site}}/{{site}}_{{year}}_combined.shp"
    conda:
        "EvergladesTools"
    shell:
        "python combine_birds_site_year.py {input}"

rule combine_predicted_birds:
    input:
        expand(f"{working_dir}/predictions/{{year}}/{{site}}/{{site}}_{{year}}_combined.shp",
               zip, site=SITES_SY, year=YEARS_SY)
    output:
        f"{working_dir}/EvergladesTools/App/Zooniverse/data/PredictedBirds.zip"
    conda:
        "EvergladesTools"
    shell:
        "python combine_bird_predictions.py {input}"

rule detect_nests:
    input:
        f"{working_dir}/predictions/{{year}}/{{site}}/{{site}}_{{year}}_combined.shp"
    output:
        f"{working_dir}/detected_nests/{{year}}/{{site}}/{{site}}_{{year}}_detected_nests.shp"
    conda:
        "EvergladesTools"
    shell:
        "python nest_detection.py {input}"

rule process_nests:
    input:
        f"{working_dir}/detected_nests/{{year}}/{{site}}/{{site}}_{{year}}_detected_nests.shp"
    output:
        f"{working_dir}/processed_nests/{{year}}/{{site}}/{{site}}_{{year}}_processed_nests.shp"
    conda:
        "EvergladesTools"
    shell:
        "python process_nests.py {input}"

rule combine_nests:
    input:
        expand(f"{working_dir}/processed_nests/{{year}}/{{site}}/{{site}}_{{year}}_processed_nests.shp",
               zip, site=SITES_SY, year=YEARS_SY)
    output:
        f"{working_dir}/EvergladesTools/App/Zooniverse/data/nest_detections_processed.zip"
    conda:
        "EvergladesTools"
    shell:
        "python combine_nests.py {input}"

rule create_mbtile:
    input:
        f"{working_dir}/projected_mosaics/webmercator/{{year}}/{{site}}/{{flight}}_projected.tif"
    output:
        f"{working_dir}/mapbox/{{year}}/{{site}}/{{flight}}.mbtiles"
    conda:
        "mbtilesenv"
    shell:
        "python mbtile.py {input} {config[mapbox-param]}"

rule upload_mapbox:
    input:
        f"{working_dir}/mapbox/{{year}}/{{site}}/{{flight}}.mbtiles"
    output:
        touch(f"{working_dir}/mapbox/last_uploaded/{{year}}/{{site}}/{{flight}}.mbtiles")
    conda:
        "EvergladesTools"
    shell:
        "python upload_mapbox.py {input}"
