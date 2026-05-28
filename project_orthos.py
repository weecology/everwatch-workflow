#!/usr/bin/env python3
import os
import sys
import traceback
from pathlib import Path
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
    warp_opts = gdal.WarpOptions(
        dstSRS=f'EPSG:{dst_crs}',
        resampleAlg='bilinear',
        multithread=True,
        # Preserve the ODM alpha band as the output mask rather than using a nodata value
        srcAlpha=True,
        dstAlpha=True,
        warpOptions=['INIT_DEST=NO_DATA'],
        creationOptions=['TILED=YES', 'COMPRESS=LZW', 'PREDICTOR=2', 'BIGTIFF=YES', 'BLOCKXSIZE=512', 'BLOCKYSIZE=512'])
    print(f"Processing {path} -> {dest_name}", flush=True)
    ds = gdal.Warp(dest_name, path, options=warp_opts)
    if ds is None:
        raise RuntimeError(f"GDAL Warp failed for {path} -> {dest_name}")
    ds = None
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
