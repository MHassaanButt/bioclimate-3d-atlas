#!/usr/bin/env python3
"""
BioClimate 3D Atlas
Author: Muhammad Hassaan Farooq Butt

Generates three output images per country:
  1. *_professional.png  — dark theme, province labels  (LinkedIn)
  2. *_public.png        — light theme, plain English + emojis  (Facebook)
  3. *_3d.png            — 3D terrain relief view

Supported data sources (auto-selected by year range):
  CHELSA V2.1    — 1981-2010 only (published on CDN)
  TerraClimate   — 1958-2024  (monthly global data, ~4 km)

Usage:
    python main.py                      # uses ACTIVE_COUNTRY from config.py
    python main.py --country NOR        # switch to Norway
    python main.py --country PAK        # switch to Pakistan
"""

import argparse
import os
import sys
import numpy as np
import geopandas as gpd
from shapely.geometry import Point

import config
from utils.data import (
    align_to, download_srtm, load_boundary, load_admin1, load_dem,
    mask_to_shape, reproject_array, select_source,
    get_chelsa, get_terraclimate_temp, get_terraclimate_prec,
)
from utils.classify import bivariate_classify
from utils.render import make_professional_map, make_public_map, make_3d_map

# ── CLI ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Generate bivariate climate maps.")
parser.add_argument("--country", default=config.ACTIVE_COUNTRY,
                    choices=list(config.COUNTRIES),
                    help="Country ISO code (default from config.py)")
args = parser.parse_args()

ISO     = args.country
CFG     = config.COUNTRIES[ISO]
NAME    = CFG["name"]
CRS     = CFG["crs"]
ISO_LOW = ISO.lower()

YEAR_START = CFG["year_start"]
YEAR_END   = CFG["year_end"]

os.makedirs("data",    exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# ── Validate year range and pick data source ──────────────────────────────────
print("=" * 62)
print(f"  BioClimate 3D Atlas  |  {NAME}  |  {YEAR_START}-{YEAR_END}")
print(f"  Author: {config.AUTHOR}")
print("=" * 62)

try:
    SOURCE = select_source(YEAR_START, YEAR_END)
except ValueError as e:
    print(f"\nConfiguration error:\n{e}")
    sys.exit(1)

PERIOD_LABEL = f"{YEAR_START}-{YEAR_END}"
print(f"\n  Data source : {SOURCE}")
print(f"  Period      : {PERIOD_LABEL}")

# ── 1. Country boundary ───────────────────────────────────────────────────────
print("\n[1/6] Loading country boundary ...")
country = load_boundary(CFG["gadm_file"], CFG["gadm_url"])
bounds  = country.total_bounds
buf     = CFG["buffer"]
pad     = (bounds[0] - buf, bounds[1] - buf, bounds[2] + buf, bounds[3] + buf)
print(f"  Bounds (WGS84): {bounds.round(2)}")

# ── 2. Province / state boundaries ───────────────────────────────────────────
print("\n[2/6] Loading province boundaries ...")
admin1_proj = None
short_names = {}

admin1_cfg = config.ADMIN1.get(ISO)
if admin1_cfg:
    admin1_raw  = load_admin1(admin1_cfg["file"], admin1_cfg["url"])
    admin1_proj = admin1_raw.to_crs(CRS)
    short_names = admin1_cfg.get("shorts", {})
    print(f"  Loaded {len(admin1_raw)} provinces/states.")
else:
    print("  No admin-1 config — skipping province labels.")

# ── 3. Major cities ───────────────────────────────────────────────────────────
print("\n[3/6] Projecting city locations ...")
cities_xy  = {}
cities_raw = config.CITIES.get(ISO, {})
if cities_raw:
    cities_gdf = gpd.GeoDataFrame(
        {"name": list(cities_raw.keys())},
        geometry=[Point(lon, lat) for lon, lat in cities_raw.values()],
        crs="EPSG:4326",
    ).to_crs(CRS)
    cities_xy = {row["name"]: (row.geometry.x, row.geometry.y)
                 for _, row in cities_gdf.iterrows()}
    print(f"  {len(cities_xy)} cities ready.")

# ── 4. Climate data ───────────────────────────────────────────────────────────
print(f"\n[4/6] Loading climate data ({SOURCE}, {PERIOD_LABEL}) ...")

if SOURCE == "CHELSA_V2.1":
    period = f"{YEAR_START}-{YEAR_END}"   # "1981-2010"
    temp_raw, temp_tr, temp_crs = get_chelsa(
        1,  f"data/{ISO_LOW}_bio1_{period}.tif",  pad, period, config.NODATA)
    prec_raw, prec_tr, prec_crs = get_chelsa(
        12, f"data/{ISO_LOW}_bio12_{period}.tif", pad, period, config.NODATA)
    # CHELSA encoding: bio1 = °C × 10, bio12 = mm/year
    temp_celsius = temp_raw / 10.0
    prec_monthly = prec_raw / 30.0    # mm/year -> avg mm/month

elif SOURCE == "TerraClimate":
    temp_raw, temp_tr, temp_crs = get_terraclimate_temp(
        YEAR_START, YEAR_END,
        f"data/{ISO_LOW}_tc_temp_{PERIOD_LABEL}.tif",
        pad, config.NODATA,
    )
    prec_raw, prec_tr, prec_crs = get_terraclimate_prec(
        YEAR_START, YEAR_END,
        f"data/{ISO_LOW}_tc_prec_{PERIOD_LABEL}.tif",
        pad, config.NODATA,
    )
    # TerraClimate: temp already in °C, prec in mm/year
    temp_celsius = temp_raw
    prec_monthly = prec_raw / 12.0    # mm/year -> avg mm/month

# ── 5. DEM ────────────────────────────────────────────────────────────────────
print(f"\n[5/6] Acquiring SRTM elevation data ...")
dem_data = dem_tr_l = dem_crs_l = None
dem_file = CFG["dem_file"]

if not os.path.exists(dem_file):
    try:
        download_srtm(pad, os.path.abspath(dem_file))
        print(f"  DEM saved -> {dem_file}")
    except Exception as exc:
        print(f"  DEM download failed: {exc}")
        print("  Will use temperature as elevation proxy for 3D view.")

if os.path.exists(dem_file):
    dem_data, dem_tr_l, dem_crs_l = load_dem(dem_file, config.MAX_DEM_PX)
    print(f"  DEM: shape={dem_data.shape}  max={np.nanmax(dem_data):.0f} m")

# ── 6. Process -> Classify -> Render ─────────────────────────────────────────
print(f"\n[6/6] Processing, classifying, and rendering ...")

temp_m, temp_m_tr = mask_to_shape(temp_celsius, temp_tr, temp_crs, country, config.NODATA)
temp_p, temp_p_tr = reproject_array(temp_m, temp_m_tr, temp_crs, CRS, config.NODATA)

prec_m, prec_m_tr = mask_to_shape(prec_monthly, prec_tr, prec_crs, country, config.NODATA)
prec_p, _         = reproject_array(prec_m, prec_m_tr, prec_crs, CRS, config.NODATA)

if prec_p.shape != temp_p.shape:
    prec_p = align_to(prec_p, temp_p.shape)

print(f"  Grid : {temp_p.shape}")
print(f"  Temp : [{np.nanmin(temp_p):.1f}, {np.nanmax(temp_p):.1f}] C")
print(f"  Prec : [{np.nanmin(prec_p):.1f}, {np.nanmax(prec_p):.1f}] mm/mo")

rows_n, cols_n = temp_p.shape
extent = [
    temp_p_tr.c,
    temp_p_tr.c + cols_n * temp_p_tr.a,
    temp_p_tr.f + rows_n * temp_p_tr.e,
    temp_p_tr.f,
]
country_proj = country.to_crs(CRS)

# Classify — DkBlue for professional, Vivid for public
pal_pro = config.PALETTES[config.PALETTE_PROFESSIONAL]
_, _, valid_pro, rgba_pro = bivariate_classify(
    temp_p, prec_p, config.N_CLASSES, pal_pro)

pal_pub = config.PALETTES[config.PALETTE_PUBLIC]
_, _, valid_pub, rgba_pub = bivariate_classify(
    temp_p, prec_p, config.N_CLASSES, pal_pub)

# Process DEM once — used for both 2D hillshade AND 3D terrain
dem_p2      = None
dem_is_real = dem_data is not None

if dem_is_real:
    dem_m2, dem_m_tr2 = mask_to_shape(dem_data, dem_tr_l, dem_crs_l, country, config.NODATA)
    dem_p2, _         = reproject_array(dem_m2, dem_m_tr2, dem_crs_l, CRS, config.NODATA)
    if dem_p2.shape != temp_p.shape:
        dem_p2 = align_to(dem_p2, temp_p.shape)
    dem_p2 = np.nan_to_num(dem_p2, nan=0.0)
    dem_p2[dem_p2 < 0] = 0
else:
    # Proxy: temperature inverted → higher = cooler → "mountain" proxy
    proxy = np.nan_to_num(temp_p, nan=0.0)
    t_min, t_max = proxy.min(), proxy.max()
    dem_p2 = (t_max - proxy) / (t_max - t_min) * 5000
    dem_p2[~valid_pub] = 0

# Shared kwargs for 2D maps
map_kw = dict(
    extent=extent, country_proj=country_proj,
    admin1_proj=admin1_proj, short_names=short_names, cities_xy=cities_xy,
    n_classes=config.N_CLASSES,
    country_name=NAME, period=PERIOD_LABEL, author=config.AUTHOR,
    dem=dem_p2 if dem_is_real else None,   # only real DEM for hillshade
)

print("\n  --- Professional map ---")
out_pro = f"outputs/{ISO_LOW}_professional.png"
make_professional_map(rgba=rgba_pro, palette=pal_pro,
                      output_path=out_pro, **map_kw)

print("\n  --- Public map ---")
out_pub = f"outputs/{ISO_LOW}_public.png"
make_public_map(rgba=rgba_pub, palette=pal_pub,
                output_path=out_pub, **map_kw)

print("\n  --- 3D terrain view ---")
out_3d = f"outputs/{ISO_LOW}_3d.png"
make_3d_map(dem_p2, rgba_pro, valid_pro, bounds,
            NAME, PERIOD_LABEL, config.AUTHOR, out_3d)


print("\n" + "=" * 62)
print("Done!  Output files:")
print(f"  {out_pro}                 <- Professional map")
print(f"  {out_pub}                    <- Public map")
# print(f"  {out_3d}                      <- 3D terrain view")
