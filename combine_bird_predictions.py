import os
import sys
import shutil
from zipfile import ZipFile, ZIP_DEFLATED
import geopandas as gpd
import pandas as pd
import tools


def combine(paths):
    """Read multiple prediction shapefiles and concatenate into one GeoDataFrame."""
    gdfs = []
    target_crs = None
    for p in paths:
        gdf = gpd.read_file(p)
        if target_crs is None:
            target_crs = gdf.crs
        elif gdf.crs != target_crs and target_crs is not None:
            # Reproject to the CRS of the first file for consistency
            gdf = gdf.to_crs(target_crs)
        gdfs.append(gdf)
    if not gdfs:
        raise ValueError("No input shapefiles provided.")
    return gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs=target_crs)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python combine_bird_predictions.py <shp1> <shp2> ...")
        sys.exit(1)

    working_dir = tools.get_working_dir()
    output_path = os.path.join(working_dir, "everwatch-workflow", "App", "Zooniverse", "data")
    os.makedirs(output_path, exist_ok=True)

    output_shp_base = os.path.join(output_path, "PredictedBirds")
    output_zip = output_shp_base + ".zip"

    # Read and combine
    predictions = sys.argv[1:]
    df = combine(predictions)

    # Write shapefile (prefer Fiona engine for Shapefile compatibility)
    try:
        df.to_file(output_shp_base + ".shp", driver="ESRI Shapefile", engine="fiona")
    except Exception:
        # Fallback to default engine if Fiona isn’t available
        df.to_file(output_shp_base + ".shp", driver="ESRI Shapefile")

    # Write summary CSV
    grouped_df = df.groupby(["Site", "Date", "label"]).size().reset_index(name="count")
    grouped_df.to_csv(output_shp_base + ".csv", index=False)

    # Zip shapefile components
    shp_exts = ["cpg", "dbf", "prj", "shp", "shx"]
    with ZipFile(output_zip, "w", compression=ZIP_DEFLATED) as zf:
        for ext in shp_exts:
            f = f"{output_shp_base}.{ext}"
            if os.path.exists(f):
                zf.write(f, arcname=os.path.basename(f))
    # Optionally clean up shapefile parts after zipping
    for ext in shp_exts:
        f = f"{output_shp_base}.{ext}"
        if os.path.exists(f):
            os.remove(f)

    # Copy PredictedBirds.zip to forecast web repo (ensure permissions)
    dest_path = os.path.join(working_dir, "everglades-forecast-web", "data")
    os.makedirs(dest_path, exist_ok=True)
    dest_file = os.path.join(dest_path, "PredictedBirds.zip")

    try:
        shutil.copy(output_zip, dest_file)
        print(f"{output_zip} copied to {dest_file}.")
    except PermissionError:
        print(f"Permission denied copying to {dest_file}. Leaving zip at {output_zip}.")