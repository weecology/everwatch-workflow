import glob
import os
import tools

configfile: "snakemake_config.yml"

ORTHOMOSAICS = glob_wildcards("/blue/ewhite/everglades/orthomosaics/{year}/{site}/{flight}.tif")
FLIGHTS = ORTHOMOSAICS.flight
SITES = ORTHOMOSAICS.site
YEARS = ORTHOMOSAICS.year
site_year_combos = {*zip(SITES, YEARS)}
SITES_SY, YEARS_SY = list(zip(*site_year_combos))

rule all:
    input:
        "/blue/ewhite/everglades/EvergladesTools/App/Zooniverse/data/PredictedBirds.zip",
        "/blue/ewhite/everglades/EvergladesTools/App/Zooniverse/data/nest_detections_processed.zip",
        expand("/blue/ewhite/everglades/predictions/{year}/{site}/{flight}_projected.shp",
               zip, site=SITES, year=YEARS, flight=FLIGHTS), #not sure if still needed
        expand("/blue/ewhite/everglades/processed_nests/{year}/{site}/{site}_{year}_processed_nests.shp",
               zip, site=SITES, year=YEARS),
        expand("/blue/ewhite/everglades/mapbox/{year}/{site}/{flight}.mbtiles",
               zip, site=SITES, year=YEARS, flight=FLIGHTS)


rule project_mosaics:
    input:
        "/blue/ewhite/everglades/orthomosaics/{year}/{site}/{flight}.tif"
    output:
        "/blue/ewhite/everglades/projected_mosaics/{year}/{site}/{flight}_projected.tif",
        "/blue/ewhite/everglades/projected_mosaics/webmercator/{year}/{site}/{flight}_projected.tif"
    shell:
        "python project_orthos.py {input}"

rule predict_birds:
    input:
        "/blue/ewhite/everglades/projected_mosaics/{year}/{site}/{flight}_projected.tif"
    output:
        "/blue/ewhite/everglades/predictions/{year}/{site}/{flight}_projected.shp"
    resources:
        gpu=1
    shell:
        "python predict.py {input}"

def flights_in_year_site(wildcards):
    basepath = "/blue/ewhite/everglades/predictions"
    flights_in_year_site = []
    for site, year, flight in zip(SITES, YEARS, FLIGHTS):
        flight_path = os.path.join(basepath, year, site, f"{flight}_projected.shp")
        event = tools.get_event(flight_path)
        if site == wildcards.site and year == wildcards.year and event == "primary":
            flights_in_year_site.append(flight_path)
    return flights_in_year_site

rule combine_birds_site_year:
    input:
        flights_in_year_site
    output:
        "/blue/ewhite/everglades/predictions/{year}/{site}/{site}_{year}_combined.shp"
    shell:
        "python combine_birds_site_year.py {input}"

rule combine_predicted_birds:
    input:
        expand("/blue/ewhite/everglades/predictions/{year}/{site}/{site}_{year}_combined.shp",
               zip, site=SITES_SY, year=YEARS_SY)
    output:
        "/blue/ewhite/everglades/EvergladesTools/App/Zooniverse/data/PredictedBirds.zip"
    shell:
        "python combine_bird_predictions.py {input}"

rule detect_nests:
    input:
        "/blue/ewhite/everglades/predictions/{year}/{site}/{site}_{year}_combined.shp"
    output:
        "/blue/ewhite/everglades/detected_nests/{year}/{site}/{site}_{year}_detected_nests.shp"
    shell:
        "python nest_detection.py {input}"

rule process_nests:
    input:
        "/blue/ewhite/everglades/detected_nests/{year}/{site}/{site}_{year}_detected_nests.shp"
    output:
        "/blue/ewhite/everglades/processed_nests/{year}/{site}/{site}_{year}_processed_nests.shp"
    shell:
        "python process_nests.py {input}"

rule combine_nests:
    input:
        expand("/blue/ewhite/everglades/processed_nests/{year}/{site}/{site}_{year}_processed_nests.shp",
               zip, site=SITES_SY, year=YEARS_SY)
    output:
        "/blue/ewhite/everglades/EvergladesTools/App/Zooniverse/data/nest_detections_processed.zip"
    shell:
        "python combine_nests.py {input}"

rule create_mbtile:
    input:
        "/blue/ewhite/everglades/projected_mosaics/webmercator/{year}/{site}/{flight}_projected.tif"
    output:
        "/blue/ewhite/everglades/mapbox/{year}/{site}/{flight}.mbtiles"
    shell:
        "python mbtile.py.py {input} {config[mapbox-param]}"

rule upload_mapbox:
    input:
        "/blue/ewhite/everglades/mapbox/{year}/{site}/{flight}.mbtiles"
    shell:
        "python upload_mapbox.py {input}"
