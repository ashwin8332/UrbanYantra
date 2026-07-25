"""Build pixel-level feature table from raster stack."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from data_ingestion.cache import save_geotiff, save_parquet
from features.feature_columns import FEATURE_COLUMNS
from features.hotspot_detection import classify_hotspots_from_gi, getis_ord_gi_star
from features.lcz_proxy import derive_lcz_proxy
from features.morphology import compute_morphology_rasters
from features.temporal import summarize_meteo_for_pixels
from features.urban_mask import apply_urban_extent_mask

logger = logging.getLogger(__name__)


def _read_raster(path: Path) -> np.ndarray:
    with rasterio.open(path) as src:
        return src.read(1).astype(np.float32)


def _resize_to_match(arr: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    """Resample a raster to the reference grid (handles mixed GEE/synthetic cache sizes)."""
    if arr.shape == target_shape:
        return arr.astype(np.float32)
    from scipy.ndimage import zoom

    zy = target_shape[0] / arr.shape[0]
    zx = target_shape[1] / arr.shape[1]
    return zoom(arr, (zy, zx), order=1).astype(np.float32)


def build_feature_stack(config: dict, out_dir: Path) -> tuple[pd.DataFrame, Path]:
    """Assemble features + LST target into parquet; export driver attribution raster."""
    raster_dir = out_dir / "rasters"
    table_path = out_dir / "tables" / "feature_table.parquet"
    lst_path = out_dir / "rasters" / "lst_10m.tif"

    if table_path.exists() and lst_path.exists() and not config.get("force_refresh"):
        cached = pd.read_parquet(table_path)
        missing = [c for c in FEATURE_COLUMNS if c not in cached.columns]
        if "is_water" not in cached.columns:
            missing.append("is_water")
        if "is_excluded" not in cached.columns:
            missing.append("is_excluded")
        if not missing:
            return cached, lst_path
        logger.info("Rebuilding feature table — cached parquet missing: %s", missing)

    ndvi = _read_raster(raster_dir / "ndvi.tif")
    ndbi = _read_raster(raster_dir / "ndbi.tif")
    ndwi = _read_raster(raster_dir / "ndwi.tif")
    utfvi = _read_raster(raster_dir / "utfvi.tif")
    lulc = _read_raster(raster_dir / "worldcover.tif")
    bheight = _read_raster(raster_dir / "ghsl_building_height.tif")
    pop = _read_raster(raster_dir / "ghsl_population.tif")

    h, w = ndvi.shape
    target_shape = (h, w)
    ndbi = _resize_to_match(ndbi, target_shape)
    ndwi = _resize_to_match(ndwi, target_shape)
    utfvi = _resize_to_match(utfvi, target_shape)
    lulc = _resize_to_match(lulc, target_shape)
    bheight = _resize_to_match(bheight, target_shape)
    pop = _resize_to_match(pop, target_shape)

    osm_path = out_dir / "tables" / "osm_morphology.parquet"
    osm_df = pd.read_parquet(osm_path)
    building_density = None
    road_density = None
    if len(osm_df) == h * w:
        building_density = osm_df["building_density"].values.reshape(h, w)
        road_density = osm_df["road_density"].values.reshape(h, w)
    elif len(osm_df) > 0:
        osm_h = int(osm_df["row"].max()) + 1
        osm_w = int(osm_df["col"].max()) + 1
        if osm_h * osm_w == len(osm_df):
            building_density = _resize_to_match(
                osm_df["building_density"].values.reshape(osm_h, osm_w), target_shape
            )
            road_density = _resize_to_match(
                osm_df["road_density"].values.reshape(osm_h, osm_w), target_shape
            )

    morph = compute_morphology_rasters(lulc, building_density, road_density)
    for name, arr in morph.items():
        save_geotiff(arr, raster_dir / f"{name}.tif", config["bbox"])

    meteo = pd.read_parquet(out_dir / "tables" / "era5_land_hourly.parquet")
    meteo_summary = summarize_meteo_for_pixels(meteo)

    lst_coarse = _resize_to_match(_read_raster(raster_dir / "landsat_lst_c.tif"), target_shape)

    # 10 m LST downscaling: regression-style residual from NDVI/NDBI (PDF recommended path)
    from preprocessing.lst_downscale import downscale_lst

    lst_10m = downscale_lst(lst_coarse, ndvi, ndbi)
    save_geotiff(lst_10m, lst_path, config["bbox"])

    import rasterio

    with rasterio.open(lst_path) as src:
        transform = src.transform

    water_class = 80
    rows = []
    for r in range(h):
        for c in range(w):
            lon, lat = rasterio.transform.xy(transform, r, c, offset="center")
            is_water = int(lulc[r, c]) == water_class
            row = {
                "row": r,
                "col": c,
                "lon": float(lon),
                "lat": float(lat),
                "is_water": is_water,
                "lst_c": float(lst_10m[r, c]),
                "ndvi": float(ndvi[r, c]),
                "ndbi": float(ndbi[r, c]),
                "ndwi": float(ndwi[r, c]),
                "utfvi": float(utfvi[r, c]),
                **{k: float(v[r, c]) for k, v in morph.items()},
                "building_height": float(bheight[r, c]),
                "population": float(pop[r, c]),
                **meteo_summary,
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    df["city"] = config.get("city_name", "city")
    lcz_grid = derive_lcz_proxy(bheight, morph["impervious_frac"])
    df["lcz_class"] = [int(lcz_grid[int(r["row"]), int(r["col"])]) for r in rows]

    hs_cfg = config.get("hotspot", {})
    gi_z, gi_p = getis_ord_gi_star(
        lst_10m,
        kernel_size=int(hs_cfg.get("gi_star_kernel", 5)),
    )
    hotspot_grid = classify_hotspots_from_gi(
        lst_10m,
        gi_z,
        gi_p,
        moderate_delta_c=hs_cfg.get("moderate_delta_c", 2.0),
        severe_delta_c=hs_cfg.get("severe_delta_c", 4.0),
        p_threshold=hs_cfg.get("gi_star_p_threshold", 0.05),
    )
    df["gi_star_z"] = [float(gi_z[int(r["row"]), int(r["col"])]) for r in rows]
    df["hotspot_class"] = [int(hotspot_grid[int(r["row"]), int(r["col"])]) for r in rows]
    df["thermal_stress_class"] = np.where(df["lst_c"] >= 40, 2, np.where(df["lst_c"] >= 37, 1, 0))
    df["tile_id"] = (
        (df["lon"] // config["spatial_cv"]["tile_size_deg"]).astype(int).astype(str)
        + "_"
        + (df["lat"] // config["spatial_cv"]["tile_size_deg"]).astype(int).astype(str)
    )

    df = apply_urban_extent_mask(df, config, out_dir)

    save_parquet(df, table_path)
    logger.info("Feature table: %d pixels, %d features", len(df), len(FEATURE_COLUMNS))
    return df, lst_path
