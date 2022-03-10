import glob
import os

ORTHOMOSAICS = glob_wildcards("/blue/ewhite/everglades/orthomosaics/{year}/{site}/{flight}.tif")

rule all:
    input:
        "/blue/ewhite/everglades/EvergladesTools/App/Zooniverse/data/PredictedBirds.zip",
        expand("/blue/ewhite/everglades/predictions/{year}/{site}/{flight}_projected.shp",
               zip, site=ORTHOMOSAICS.site, year = ORTHOMOSAICS.year, flight=ORTHOMOSAICS.flight)


rule project_mosaics:
    input:
        "/blue/ewhite/everglades/orthomosaics/{year}/{site}/{flight}.tif"
    output:
        "/blue/ewhite/everglades/projected_mosaics/{year}/{site}/{flight}_projected.tif"
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

rule combine_predicted_birds:
    input:
        expand("/blue/ewhite/everglades/predictions/{year}/{site}/{flight}_projected.shp",
               zip, site=ORTHOMOSAICS.site, year = ORTHOMOSAICS.year, flight=ORTHOMOSAICS.flight)
    output:
        "/blue/ewhite/everglades/EvergladesTools/App/Zooniverse/data/PredictedBirds.zip"
    shell:
        "python combine_bird_predictions.py"
