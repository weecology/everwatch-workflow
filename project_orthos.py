#!/usr/bin/env python3
import os
import sys
import traceback
from pathlib import Path
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
    # Keep RGB only (drop any ODM alpha band) so the output stays 3-band for deepforest
    src_vrt = gdal.Translate('', path, options=gdal.TranslateOptions(format='VRT', bandList=[1, 2, 3]))
    for i in range(1, 4):
        src_vrt.GetRasterBand(i).SetNoDataValue(nodata_value)
    warp_opts = gdal.WarpOptions(
        dstSRS=f'EPSG:{dst_crs}',
        resampleAlg='bilinear',
        multithread=True,
        srcNodata=nodata_value,
        dstNodata=nodata_value,
        warpOptions=['INIT_DEST=NO_DATA', 'UNIFIED_SRC_NODATA=YES'],
        creationOptions=['TILED=YES', 'COMPRESS=LZW', 'PREDICTOR=2', 'BIGTIFF=YES', 'BLOCKXSIZE=512', 'BLOCKYSIZE=512'])
    print(f"Processing {path} -> {dest_name}", flush=True)
    ds = gdal.Warp(dest_name, src_vrt, options=warp_opts)
    if ds is None:
        raise RuntimeError(f"GDAL Warp failed for {path} -> {dest_name}")
    ds = None
    src_vrt = None
    return dest_name


if __name__ == "__main__":
    try:
        path = sys.argv[1]
        working_dir = tools.get_working_dir()
        # Extract year/site relative to the orthomosaics dir rather than using fixed indices
        rel = Path(path).relative_to(Path(working_dir) / "orthomosaics")
        year, site = rel.parts[0], rel.parts[1]

        out1 = project_raster(path,
                              year,
                              site,
                              dst_crs=32617,
                              savedir=f"{working_dir}/projected_mosaics/")
        print(f"Wrote: {out1}", flush=True)

        out2 = project_raster(path,
                              year,
                              site,
                              dst_crs=3857,
                              savedir=f"{working_dir}/projected_mosaics/webmercator/")
        print(f"Wrote: {out2}", flush=True)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
