"""Data download, caching, and raster processing utilities."""

import io
import os
import zipfile
import warnings
from textwrap import dedent

import numpy as np
import requests
import geopandas as gpd
import rasterio
from rasterio.mask import mask as rio_mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.windows import from_bounds as window_from_bounds
import rasterio.transform as rio_transform_mod
from scipy.ndimage import zoom as ndimage_zoom
from shapely.geometry import mapping

warnings.filterwarnings("ignore")

CHELSA_BASE    = "https://os.zhdk.cloud.switch.ch/chelsav2/GLOBAL/climatologies"
TERRACLIMATE_BASE = "https://climate.northwestknowledge.net/TERRACLIMATE-DATA"

# Authoritative year limits per source (mirrors what config.DATA_SOURCES says)
_CHELSA_RANGE      = (1981, 2010)
_TERRACLIMATE_RANGE = (1958, 2024)


# ── Source validation ─────────────────────────────────────────────────────────

def select_source(year_start: int, year_end: int) -> str:
    """
    Return the data-source name for the requested year range,
    or raise a clear ValueError listing what is available.

    Returns: "CHELSA_V2.1" | "TerraClimate"
    """
    if year_start < 1 or year_end < year_start:
        raise ValueError(
            f"Invalid year range: {year_start}-{year_end}. "
            "year_start must be >= 1 and <= year_end."
        )

    cs, ce = _CHELSA_RANGE
    ts, te = _TERRACLIMATE_RANGE

    if cs <= year_start and year_end <= ce:
        return "CHELSA_V2.1"
    if ts <= year_start and year_end <= te:
        return "TerraClimate"

    raise ValueError(dedent(f"""
        No data source covers {year_start}–{year_end}.

        Available sources:
          CHELSA V2.1    : {cs}–{ce}  (only this period is published)
          TerraClimate   : {ts}–{te}  (monthly, ~4 km resolution)

        Fix: set year_start / year_end inside COUNTRIES[...] in config.py
        to a range fully covered by one of the sources above.
    """).strip())


# ── Boundary loaders ──────────────────────────────────────────────────────────

def load_boundary(gadm_file: str, gadm_url: str) -> gpd.GeoDataFrame:
    """Download (if needed) and return the country level-0 boundary."""
    os.makedirs(os.path.dirname(gadm_file), exist_ok=True)
    if not os.path.exists(gadm_file):
        print(f"  Downloading boundary -> {gadm_file}")
        r = requests.get(gadm_url, timeout=120)
        r.raise_for_status()
        with open(gadm_file, "wb") as f:
            f.write(r.content)
    return gpd.read_file(gadm_file).to_crs("EPSG:4326")


def load_admin1(gadm_file: str, gadm_url: str) -> gpd.GeoDataFrame:
    """Download (if needed) and return the province/state level-1 boundaries."""
    os.makedirs(os.path.dirname(gadm_file), exist_ok=True)
    if not os.path.exists(gadm_file):
        print(f"  Downloading admin-1 boundaries -> {gadm_file}")
        r = requests.get(gadm_url, timeout=180)
        r.raise_for_status()
        with open(gadm_file, "wb") as f:
            f.write(r.content)
    return gpd.read_file(gadm_file).to_crs("EPSG:4326")


# ── CHELSA V2.1 ───────────────────────────────────────────────────────────────

def get_chelsa(bio_id: int, local_name: str, pad_bounds: tuple,
               period: str, nodata: float):
    """
    Return (data, transform, crs) for a CHELSA bioclimatic variable.
    Units returned: bio1 is °C × 10, bio12 is mm/year (caller applies /10 and /30).
    """
    os.makedirs(os.path.dirname(local_name), exist_ok=True)
    if os.path.exists(local_name):
        print(f"  [{os.path.basename(local_name)}] cached.")
        with rasterio.open(local_name) as src:
            data = src.read(1).astype(float)
            if src.nodata is not None:
                data[data == src.nodata] = np.nan
            return data, src.transform, src.crs

    filename   = f"CHELSA_bio{bio_id}_{period}_V.2.1.tif"
    remote_url = f"{CHELSA_BASE}/{period}/bio/{filename}"
    vsicurl    = f"/vsicurl/{remote_url}"

    print(f"  Fetching CHELSA bio{bio_id} ({period}) via /vsicurl ...")
    try:
        with rasterio.open(vsicurl) as src:
            win  = window_from_bounds(*pad_bounds, src.transform)
            data = src.read(1, window=win).astype(float)
            wtr  = src.window_transform(win)
            if src.nodata is not None:
                data[data == src.nodata] = np.nan
            meta = {**src.meta, "height": data.shape[0],
                    "width": data.shape[1], "transform": wtr, "dtype": "float32"}
            with rasterio.open(local_name, "w", **meta) as dst:
                dst.write(data.astype("float32"), 1)
            return data, wtr, src.crs
    except Exception as exc:
        print(f"  vsicurl failed ({exc}); downloading full file ...")
        full = f"_chelsa_bio{bio_id}_full.tif"
        r = requests.get(remote_url, stream=True, timeout=7200)
        r.raise_for_status()
        with open(full, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        with rasterio.open(full) as src:
            win  = window_from_bounds(*pad_bounds, src.transform)
            data = src.read(1, window=win).astype(float)
            wtr  = src.window_transform(win)
            if src.nodata is not None:
                data[data == src.nodata] = np.nan
            meta = {**src.meta, "height": data.shape[0],
                    "width": data.shape[1], "transform": wtr, "dtype": "float32"}
            with rasterio.open(local_name, "w", **meta) as dst:
                dst.write(data.astype("float32"), 1)
        return data, wtr, src.crs


# ── TerraClimate ──────────────────────────────────────────────────────────────
# Variables used:
#   tmax  — monthly max temperature (°C, GDAL applies scale_factor automatically)
#   tmin  — monthly min temperature (°C)
#   ppt   — monthly precipitation   (mm)
# Resolution: 1/24 degree (~4 km).  Coverage: 1958-2024, global.

def _tc_read_year(var: str, year: int, pad_bounds: tuple):
    """
    Stream one TerraClimate annual file via /vsicurl.
    Returns array of shape (12, H, W) — 12 monthly bands — plus transform and CRS.
    Falls back to a direct HTTP download if vsicurl is not supported.
    """
    fname = f"TerraClimate_{var}_{year}.nc"
    url   = f"{TERRACLIMATE_BASE}/{fname}"

    # GDAL NetCDF subdataset via vsicurl
    vsicurl_path = f"NETCDF:/vsicurl/{url}:{var}"
    try:
        with rasterio.open(vsicurl_path) as src:
            win  = window_from_bounds(*pad_bounds, src.transform)
            data = src.read(window=win).astype(float)   # (12, H, W)
            _mask_nodata(data, src.nodata)
            return data, src.window_transform(win), src.crs
    except Exception:
        pass  # fall through to direct download

    # Direct download (cached temporarily)
    tmp = f"_tc_{var}_{year}.nc"
    if not os.path.exists(tmp):
        print(f"    vsicurl unavailable — downloading {fname} (~100 MB) ...")
        r = requests.get(url, stream=True, timeout=3600)
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)

    subdataset = f"NETCDF:{tmp}:{var}"
    with rasterio.open(subdataset) as src:
        win  = window_from_bounds(*pad_bounds, src.transform)
        data = src.read(window=win).astype(float)
        _mask_nodata(data, src.nodata)
        return data, src.window_transform(win), src.crs


def _mask_nodata(arr: np.ndarray, nodata_val):
    if nodata_val is not None:
        arr[arr == nodata_val] = np.nan


def get_terraclimate_temp(year_start: int, year_end: int,
                          local_name: str, pad_bounds: tuple, nodata: float):
    """
    Compute mean annual temperature (°C) averaged over year_start..year_end.
    Mean temp = mean of monthly (tmax + tmin) / 2.
    Returns (data_celsius, transform, crs).
    """
    os.makedirs(os.path.dirname(local_name), exist_ok=True)
    if os.path.exists(local_name):
        print(f"  [{os.path.basename(local_name)}] cached.")
        with rasterio.open(local_name) as src:
            data = src.read(1).astype(float)
            if src.nodata is not None:
                data[data == src.nodata] = np.nan
            return data, src.transform, src.crs

    yearly_means, tr_out, crs_out = [], None, None
    n_years = year_end - year_start + 1

    for year in range(year_start, year_end + 1):
        print(f"  TerraClimate temperature  {year}/{year_end} ...")
        try:
            tmax, tr, crs = _tc_read_year("tmax", year, pad_bounds)
            tmin, _,  _   = _tc_read_year("tmin", year, pad_bounds)
            # Align tmin to tmax shape if they differ slightly
            if tmin.shape != tmax.shape:
                tmin = np.stack([
                    ndimage_zoom(tmin[i], (tmax.shape[1]/tmin.shape[1],
                                           tmax.shape[2]/tmin.shape[2]), order=1)
                    for i in range(tmin.shape[0])
                ])
            tmean_monthly = (tmax + tmin) / 2.0    # (12, H, W)
            yearly_means.append(np.nanmean(tmean_monthly, axis=0))  # annual mean
            if tr_out is None:
                tr_out, crs_out = tr, crs
        except Exception as exc:
            print(f"    Warning: skipping {year} — {exc}")

    if not yearly_means:
        raise RuntimeError(
            f"TerraClimate: failed to retrieve temperature for any year in "
            f"{year_start}-{year_end}. Check your internet connection."
        )

    result = np.nanmean(yearly_means, axis=0)
    _save_tif(result, tr_out, crs_out, local_name, nodata)
    print(f"  Temperature mean cached -> {local_name}")
    return result, tr_out, crs_out


def get_terraclimate_prec(year_start: int, year_end: int,
                          local_name: str, pad_bounds: tuple, nodata: float):
    """
    Compute mean annual precipitation (mm/year) averaged over year_start..year_end.
    Returns (data_mm_per_year, transform, crs).
    """
    os.makedirs(os.path.dirname(local_name), exist_ok=True)
    if os.path.exists(local_name):
        print(f"  [{os.path.basename(local_name)}] cached.")
        with rasterio.open(local_name) as src:
            data = src.read(1).astype(float)
            if src.nodata is not None:
                data[data == src.nodata] = np.nan
            return data, src.transform, src.crs

    yearly_totals, tr_out, crs_out = [], None, None

    for year in range(year_start, year_end + 1):
        print(f"  TerraClimate precipitation {year}/{year_end} ...")
        try:
            ppt, tr, crs = _tc_read_year("ppt", year, pad_bounds)
            yearly_totals.append(np.nansum(ppt, axis=0))   # annual total
            if tr_out is None:
                tr_out, crs_out = tr, crs
        except Exception as exc:
            print(f"    Warning: skipping {year} — {exc}")

    if not yearly_totals:
        raise RuntimeError(
            f"TerraClimate: failed to retrieve precipitation for any year in "
            f"{year_start}-{year_end}. Check your internet connection."
        )

    result = np.nanmean(yearly_totals, axis=0)
    _save_tif(result, tr_out, crs_out, local_name, nodata)
    print(f"  Precipitation mean cached -> {local_name}")
    return result, tr_out, crs_out


def _save_tif(data, transform, crs, path, nodata):
    arr = data.astype("float32")
    arr[np.isnan(arr)] = nodata
    meta = {
        "driver": "GTiff", "dtype": "float32", "nodata": nodata,
        "width": data.shape[1], "height": data.shape[0],
        "count": 1, "crs": crs, "transform": transform,
    }
    with rasterio.open(path, "w", **meta) as dst:
        dst.write(arr, 1)


# ── DEM ───────────────────────────────────────────────────────────────────────

def download_srtm(bounds: tuple, output_file: str, nodata: int = -32768):
    """Download and merge CGIAR-CSI SRTM-3 tiles for the given bounding box."""
    from rasterio.merge import merge as rio_merge

    minx, miny, maxx, maxy = bounds
    col_min = max(1,  int((minx + 180) / 5) + 1)
    col_max = min(72, int((maxx + 180) / 5) + 1)
    row_min = max(1,  int((60 - maxy) / 5) + 1)
    row_max = min(24, int((60 - miny) / 5) + 1)

    our_cache  = os.path.expanduser("~/.cache/srtm_tiles")
    elev_cache = os.path.expanduser("~/.cache/elevation/SRTM3")
    os.makedirs(our_cache, exist_ok=True)

    tile_paths = []
    for col in range(col_min, col_max + 1):
        for row in range(row_min, row_max + 1):
            name      = f"srtm_{col:02d}_{row:02d}.tif"
            target    = os.path.join(our_cache, name)
            elev_tile = os.path.join(elev_cache, name)
            if not os.path.exists(target) and os.path.exists(elev_tile):
                target = elev_tile
            if not os.path.exists(target):
                url = (
                    "https://srtm.csi.cgiar.org/wp-content/uploads/files"
                    f"/srtm_5x5/TIFF/srtm_{col:02d}_{row:02d}.zip"
                )
                print(f"    Fetching {name} ...")
                try:
                    r = requests.get(url, timeout=180, stream=True)
                    r.raise_for_status()
                    raw = b"".join(r.iter_content(65536))
                    with zipfile.ZipFile(io.BytesIO(raw)) as z:
                        for member in z.namelist():
                            if member.lower().endswith(".tif"):
                                with open(target, "wb") as f:
                                    f.write(z.read(member))
                                break
                except Exception as exc:
                    print(f"    Warning: {name}: {exc}")
                    continue
            if os.path.exists(target):
                tile_paths.append(target)

    if not tile_paths:
        raise RuntimeError("No SRTM tiles found.")

    print(f"    Merging {len(tile_paths)} tile(s) ...")
    srcs = [rasterio.open(p) for p in tile_paths]
    try:
        merged, transform = rio_merge(srcs, bounds=bounds, nodata=nodata)
        meta = srcs[0].meta.copy()
        meta.update(driver="GTiff", height=merged.shape[1],
                    width=merged.shape[2], transform=transform, nodata=nodata)
        with rasterio.open(output_file, "w", **meta) as dst:
            dst.write(merged)
    finally:
        for s in srcs:
            s.close()


def load_dem(dem_file: str, max_px: int):
    """Load DEM, downsample to max_px on longest side. Returns (data, transform, crs)."""
    with rasterio.open(dem_file) as src:
        scale  = min(1.0, max_px / max(src.height, src.width))
        new_h  = max(1, int(src.height * scale))
        new_w  = max(1, int(src.width  * scale))
        data   = src.read(1, out_shape=(new_h, new_w),
                          resampling=Resampling.bilinear).astype(float)
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        data[~np.isnan(data) & (data < 0)] = 0
        tr = src.transform * src.transform.scale(src.width / new_w, src.height / new_h)
        return data, tr, src.crs


# ── Raster helpers ────────────────────────────────────────────────────────────

def _write_temp_tif(data, transform, crs, path, nodata):
    arr = data.astype("float32")
    arr[np.isnan(arr)] = nodata
    meta = {
        "driver": "GTiff", "dtype": "float32", "nodata": nodata,
        "width": data.shape[1], "height": data.shape[0],
        "count": 1, "crs": crs, "transform": transform,
    }
    with rasterio.open(path, "w", **meta) as dst:
        dst.write(arr, 1)


def mask_to_shape(data, data_tr, data_crs, shapes_gdf, nodata):
    tmp = "_tmp_mask.tif"
    _write_temp_tif(data, data_tr, data_crs, tmp, nodata)
    geoms = [mapping(g) for g in shapes_gdf.to_crs(data_crs).geometry]
    with rasterio.open(tmp) as src:
        out, out_tr = rio_mask(src, geoms, crop=True, nodata=nodata)
    os.remove(tmp)
    result = out[0].astype(float)
    result[result == nodata] = np.nan
    return result, out_tr


def reproject_array(data, data_tr, src_crs, dst_crs, nodata):
    arr = data.astype("float32")
    arr[np.isnan(arr)] = nodata
    b = rio_transform_mod.array_bounds(data.shape[0], data.shape[1], data_tr)
    dst_tr, dst_w, dst_h = calculate_default_transform(
        src_crs, dst_crs, data.shape[1], data.shape[0], *b)
    dst_arr = np.full((dst_h, dst_w), nodata, dtype="float32")
    reproject(
        source=arr, destination=dst_arr,
        src_transform=data_tr, src_crs=src_crs,
        dst_transform=dst_tr, dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=nodata, dst_nodata=nodata,
    )
    result = dst_arr.astype(float)
    result[result == nodata] = np.nan
    return result, dst_tr


def align_to(arr: np.ndarray, target_shape: tuple) -> np.ndarray:
    zy = target_shape[0] / arr.shape[0]
    zx = target_shape[1] / arr.shape[1]
    return ndimage_zoom(arr, (zy, zx), order=1)
