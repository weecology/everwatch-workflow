import geopandas
import pandas as pd
import sys
import os
import tools


def count_max_consec_detects(nest_data: pd.DataFrame, date_data: pd.DataFrame) -> int:
    """Determine the maximum number of consecutive bird detections."""
    assert date_data.shape[0] == 1, "date_data should be a DataFrame with one row"
    # Normalize to datetime and build an ordered index of dates observed at the site-year
    all_dates = sorted(pd.to_datetime(d) for d in date_data.loc[0, "Date"])
    pos = {d: i for i, d in enumerate(all_dates)}
    idxs = sorted(pos.get(pd.to_datetime(d)) for d in nest_data["Date"].unique() if pd.to_datetime(d) in pos)
    idxs = [i for i in idxs if i is not None]
    if not idxs:
        return 0
    longest = cur = 1
    for i in range(1, len(idxs)):
        if idxs[i] - idxs[i - 1] == 1:
            cur += 1
        else:
            longest = max(longest, cur)
            cur = 1
    return max(longest, cur)


def process_nests(nest_file, year, site, savedir, min_score=0.3, min_detections=3, min_consec_detects=1):
    """Process nests into a one-row-per-nest table and write a shapefile."""
    SCHEMA = {
        "geometry": "Point",
        "properties": {
            "nest_id": "int",
            "Site": "str",
            "Year": "str",
            "xmean": "float",
            "ymean": "float",
            "first_obs": "str",
            "last_obs": "str",
            "num_obs": "int",
            "species": "str",
            "sum_top1": "float",
            "num_top1": "int",
            "bird_match": "str",
        },
    }

    nests_data = geopandas.read_file(nest_file)

    # Build date_data: single row with all dates for the site-year
    date_data = (nests_data.groupby(["Site", "Year"]).agg({
        "Date": lambda x: pd.Series(x).unique().tolist()
    }).reset_index())

    target_inds = nests_data["target_ind"].unique()
    nests_rows = []

    for target_ind in target_inds:
        nest_data = nests_data[(nests_data["target_ind"] == target_ind) & (nests_data["score"] >= min_score)]
        num_consec_detects = count_max_consec_detects(nest_data, date_data)

        if len(nest_data) >= min_detections or num_consec_detects >= min_consec_detects:
            # Aggregate scores per label and pick the top label by summed score
            summed_scores = (nest_data.groupby(["Site", "Year", "target_ind",
                                                "label"])["score"].agg(["sum", "count"]).reset_index())
            top_idx = summed_scores["sum"].idxmax()
            top_score_data = summed_scores.loc[top_idx]

            # Summary stats
            nest_info = (nest_data.groupby(["Site", "Year", "target_ind"]).agg({
                "Date": ["min", "max", "count"],
                "match_xmin": ["mean"],
                "match_xmax": ["mean"],
                "match_ymin": ["mean"],
                "match_ymax": ["mean"],
            }))
            xmean = (nest_info['match_xmin']['mean'][0] + nest_info['match_xmax']['mean']) / 2
            ymean = (nest_info['match_ymin']['mean'][0] + nest_info['match_ymax']['mean']) / 2
            # Flatten date stats
            first_obs = nest_info[("Date", "min")].values[0]
            last_obs = nest_info[("Date", "max")].values[0]
            num_obs = int(nest_info[("Date", "count")].values[0])

            bird_match = ",".join(str(x) for x in nest_data["bird_id"])

            nests_rows.append([
                int(target_ind),
                str(top_score_data["Site"]),
                str(top_score_data["Year"]),
                float(xmean),
                float(ymean),
                str(first_obs),
                str(last_obs),
                int(num_obs),
                str(top_score_data["label"]),
                float(top_score_data["sum"]),
                int(top_score_data["count"]),
                bird_match,
            ])

    os.makedirs(savedir, exist_ok=True)
    filename = os.path.join(savedir, f"{site}_{year}_processed_nests.shp")

    gdf_tofile = None
    if nests_rows:
        nests_df = pd.DataFrame(nests_rows, columns=list(SCHEMA["properties"].keys()))
        nests_gdf = geopandas.GeoDataFrame(
            nests_df,
            geometry=geopandas.points_from_xy(nests_df.xmean, nests_df.ymean),
            crs=nests_data.crs,
        )
        gdf_tofile = nests_gdf
    else:
        empty_data = {
            k: pd.Series(dtype="int64" if v == "int" else "float64" if v == "float" else "object")
            for k, v in SCHEMA["properties"].items()
        }
        empty_gdf = geopandas.GeoDataFrame(
            empty_data,
            geometry=geopandas.GeoSeries([], dtype="geometry"),
            crs=nests_data.crs,
        )
        gdf_tofile = empty_gdf

    try:
        import pyogrio
        gdf_tofile.to_file(filename, driver="ESRI Shapefile", engine="pyogrio")
    except ImportError:
        gdf_tofile.to_file(filename, driver="ESRI Shapefile", engine="fiona")


if __name__ == "__main__":
    working_dir = tools.get_working_dir()
    path = sys.argv[1]
    split_path = os.path.normpath(path).split(os.path.sep)
    year = split_path[5]
    site = split_path[6]
    nestdir = os.path.join(working_dir, "processed_nests", year, site)
    process_nests(path, year, site, savedir=nestdir)
