import os
import sys

import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling


def project_raster(path, year, site, dst_crs, savedir):
    dest_path = os.path.join(savedir, year, site)
    if not os.path.exists(dest_path):
        os.makedirs(dest_path)
    basename = os.path.basename(os.path.splitext(path)[0])
    dest_name = os.path.join(dest_path, basename + "_projected.tif")

    with rasterio.open(path) as src:
        transform, width, height = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds)
        kwargs = src.meta.copy()
        kwargs.update({
            'crs': rasterio.crs.CRS.from_epsg(dst_crs),
            'transform': transform,
            'width': width,
            'height': height
        })

        with rasterio.open(dest_name, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(source=rasterio.band(src, i),
                          destination=rasterio.band(dst, i),
                          src_transform=src.transform,
                          src_crs=src.crs,
                          dst_transform=transform,
                          dst_crs=dst_crs,
                          resampling=Resampling.nearest)

    return dest_name


if __name__ == "__main__":
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]

    test_env_name = "TEST_ENV"
    test_env_set = os.environ.get(test_env_name)
    working_dir = "/blue/ewhite/everglades_test" if test_env_set else "/blue/ewhite/everglades"

    # Project into Everglades UTM zone
    project_raster(path, year, site, dst_crs=32617, savedir=f"{working_dir}/projected_mosaics/")
    # Project into webmercator for mapbox
    project_raster(path, year, site, dst_crs=3857, savedir=f"{working_dir}/projected_mosaics/webmercator/")
