#!/usr/bin/env python3
import os
import sys
from osgeo import gdal
import tools

gdal.UseExceptions()
gdal.SetConfigOption('GDAL_NUM_THREADS', 'ALL_CPUS')


def project_raster(path, year, site, dst_crs, savedir, nodata_value=255):
    dest_path = os.path.join(savedir, year, site)
    os.makedirs(dest_path, exist_ok=True)

    basename = os.path.basename(os.path.splitext(path)[0])
    dest_name = os.path.join(dest_path, basename + "_projected.tif")

    if os.path.exists(dest_name):
        gdal.Unlink(dest_name)
    # Build VRT with bands 1–3
    translate_opts = gdal.TranslateOptions(format='VRT', bandList=[1, 2, 3])
    src_vrt = gdal.Translate('', path, options=translate_opts)
    # Force the same nodata in every band of the VRT
    for i in range(1, 4):
        src_vrt.GetRasterBand(i).SetNoDataValue(nodata_value)
    warp_opts = gdal.WarpOptions(
        srcSRS='EPSG:4326',
        dstSRS=f'EPSG:{dst_crs}',
        resampleAlg='bilinear',
        multithread=True,
        srcNodata=nodata_value,
        dstNodata=nodata_value,
        warpOptions=['INIT_DEST=NO_DATA', 'UNIFIED_SRC_NODATA=YES'],
        creationOptions=['TILED=YES', 'COMPRESS=LZW', 'PREDICTOR=2', 'BIGTIFF=YES', 'BLOCKXSIZE=512', 'BLOCKYSIZE=512'])
    print(f"Processing {path} -> {dest_name}")
    ds = gdal.Warp(dest_name, src_vrt, options=warp_opts)
    if ds is None:
        raise RuntimeError(f"GDAL Warp failed for {path} -> {dest_name}")
    ds = None
    src_vrt = None
    return dest_name


if __name__ == "__main__":
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]
    working_dir = tools.get_working_dir()

    out1 = project_raster(path,
                          year,
                          site,
                          dst_crs=32617,
                          savedir=f"{working_dir}/projected_mosaics/",
                          nodata_value=255)
    print(f"Wrote: {out1}")

    out2 = project_raster(path,
                          year,
                          site,
                          dst_crs=3857,
                          savedir=f"{working_dir}/projected_mosaics/webmercator/",
                          nodata_value=255)
    print(f"Wrote: {out2}")
