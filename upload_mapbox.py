import glob
import os
import sys
import subprocess

import rasterio as rio
from rasterio.warp import calculate_default_transform, reproject, Resampling

def upload(path, year, site):
    try:
        # Create output filename
        basename = os.path.splitext(os.path.basename(path))[0]
        mbtiles_filename = "/blue/ewhite/everglades/mapbox/{}.mbtiles".format(basename)
        if os.path.exists(mbtiles_filename):
            return mbtiles_filename
          
        # Project to web mercator
        dst_crs = rio.crs.CRS.from_epsg("3857")
        with rio.open(path) as src:
            print("Transforming file into web mercator")
            transform, width, height = calculate_default_transform(
                src.crs, dst_crs, src.width, src.height, *src.bounds)
            kwargs = src.meta.copy()
            kwargs.update({
                    'crs': dst_crs,
                    'transform': transform,
                    'width': width,
                    'height': height
            })

            flight = os.path.splitext(os.path.split(path)[1])[0]
            out_filename = f"/blue/ewhite/everglades/projected_mosaics/webmercator/{year}/{site}/{flight}_projected.tif"
            if not os.path.exists(out_filename):
                with rio.open(out_filename, 'w', **kwargs) as dst:
                    for i in range(1, src.count + 1):
                        reproject(
                               source=rio.band(src, i),
                               destination=rio.band(dst, i),
                               src_transform=src.transform,
                               src_crs=src.crs,
                               dst_transform=transform,
                               dst_crs=dst_crs,
                               resampling=Resampling.nearest)
     
        # Generate tiles
        print("Creating mbtiles file")
        subprocess.run(["rio", "mbtiles", out_filename, "-o", mbtiles_filename, "--zoom-levels", "17..24", "-j", "4", "-f", "PNG", "--progress-bar"])

        # Upload to mapbox
        print("Uploading to mapbox")
        subprocess.run(["mapbox", "upload", f"bweinstein.{basename}", mbtiles_filename])
     
    except Exception as e:
        return "path: {} raised: {}".format(path, e)
          
    return mbtiles_filename

if __name__=="__main__":
     
     files_to_upload = glob.glob("/blue/ewhite/everglades/orthomosaics/2022/**/*.tif", recursive=True)
     files_to_upload = [x for x in files_to_upload if "projected" not in x]

     for index, path in enumerate(files_to_upload):
        print(f"Uploading file {path} ({index + 1}/{len(files_to_upload)})")
        split_path = os.path.normpath(path).split(os.path.sep)
        year = split_path[5]
        site = split_path[6]
        upload(path, year, site)
