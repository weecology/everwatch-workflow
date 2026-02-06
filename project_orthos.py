#!/usr/bin/env python3
import os
import sys
from osgeo import gdal
import tools

gdal.UseExceptions()
gdal.SetConfigOption('GDAL_NUM_THREADS', 'ALL_CPUS')

def project_raster(path, year, site, dst_crs, savedir):
    dest_path = os.path.join(savedir, year, site)
    os.makedirs(dest_path, exist_ok=True)

    basename = os.path.basename(os.path.splitext(path)[0])
    dest_name = os.path.join(dest_path, basename + "_projected.tif")

    if os.path.exists(dest_name):
        gdal.Unlink(dest_name)

    opts = gdal.WarpOptions(
        srcSRS='EPSG:4326',
        dstSRS=f'EPSG:{dst_crs}',
        resampleAlg='bilinear',
        multithread=True,
        creationOptions=['TILED=YES', 'COMPRESS=LZW', 'PREDICTOR=2', 'BIGTIFF=YES']
    )
    ds = gdal.Warp(dest_name, path, options=opts)
    if ds is None:
        raise RuntimeError(f"GDAL Warp failed for {path} -> {dest_name}")
    ds = None  # close

    return dest_name

if __name__ == "__main__":
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]

    working_dir = tools.get_working_dir()

    # Project into Everglades UTM zone
    out1 = project_raster(path, year, site, dst_crs=32617, savedir=f"{working_dir}/projected_mosaics/")
    print(f"Wrote: {out1}")

    # Project into Web Mercator for mapbox
    out2 = project_raster(path, year, site, dst_crs=3857, savedir=f"{working_dir}/projected_mosaics/webmercator/")
    print(f"Wrote: {out2}")