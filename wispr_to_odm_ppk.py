#!/usr/bin/env python3
"""Convert WISPR exif_image_list.csv to OpenDroneMap geo.txt format."""

import argparse
import csv

import tools

parser = argparse.ArgumentParser(description="Convert WISPR CSV to ODM geo.txt")
parser.add_argument("root_dir", help="Root directory to search for exif_image_list.csv")
parser.add_argument("output_txt", help="Output geo.txt file for ODM")
args = parser.parse_args()

csv_file = tools.find_ppk_csv(args.root_dir)
if csv_file is None:
    raise SystemExit("Error: No exif_image_list.csv found")

with open(csv_file) as infile, open(args.output_txt, "w") as outfile:
    reader = csv.DictReader(infile)
    outfile.write("EPSG:4326\n")

    for row in reader:
        # ODM format: filename lon lat alt yaw pitch roll [h_acc v_acc]
        outfile.write(f"{row['image_name']} {row['longitude']} {row['latitude']} "
                      f"{row['altitude']} {row['gimbal_yaw']} {row['gimbal_pitch']} "
                      f"{row['gimbal_roll']} {row['x_accuracy']} {row['z_accuracy']}\n")

print(f"Created {args.output_txt}")