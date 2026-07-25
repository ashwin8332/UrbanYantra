"""Raster heatmap PNG + fine pixel-aligned grid for map visualization."""

from __future__ import annotations

import io
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from geography.ward_seeds import nearest_ward_name as _nearest_ward_name
from features.display_pixels import visible_pixels
from utils import load_city_config

from backend.app.services.thermal_mask import data_bbox_from_pixels, land_visible_mask

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]

# step=2 → 60×60 cells (~3.6k); step=1 → full 120×120 (14.4k, heavier)
DEFAULT_GRID_STEP = 2
MAX_GRID_FEATURES = 14400
MAX_SAMPLE_POINTS = 12000


def _try_import_rasterio():
    try:
        import rasterio

        return rasterio
    except ImportError:
        return None


def _grid_from_column(df: pd.DataFrame, column: str) -> np.ndarray:
    """Build a row×col raster from the feature table (no GDAL)."""
    h = int(df["row"].max()) + 1
    w = int(df["col"].max()) + 1
    arr = np.full((h, w), np.nan, dtype=np.float32)
    for _, row in df.iterrows():
        arr[int(row["row"]), int(row["col"])] = float(row[column])
    return arr


def _city_out_dir(city_key: str) -> Path:
    cfg = load_city_config(ROOT / "configs" / "cities.yaml", city_key)
    return ROOT / cfg["output_dir"]


def _read_raster(path: Path) -> np.ndarray:
    rasterio = _try_import_rasterio()
    if rasterio is None or not path.exists():
        raise FileNotFoundError(path)
    with rasterio.open(path) as src:
        return src.read(1).astype(np.float32)


def _normalize_built_surface(arr: np.ndarray) -> np.ndarray:
    """Scale GHSL built-surface m² to 0–1 density for map display."""
    finite = arr[np.isfinite(arr) & (arr > 0)]
    if finite.size == 0:
        return np.zeros_like(arr, dtype=np.float32)
    p98 = float(np.percentile(finite, 98))
    return np.clip(arr / (p98 + 1e-6), 0, 1).astype(np.float32)


@lru_cache(maxsize=16)
def _load_feature_table(city_key: str) -> pd.DataFrame:
    return pd.read_parquet(_city_out_dir(city_key) / "tables" / "feature_table.parquet")


def _raster_bounds(city_key: str, df: pd.DataFrame | None = None) -> tuple[float, float, float, float]:
    raster_dir = _city_out_dir(city_key) / "rasters"
    lst_tif = raster_dir / "lst_10m.tif"
    rasterio = _try_import_rasterio()
    if rasterio is not None and lst_tif.exists():
        with rasterio.open(lst_tif) as src:
            b = src.bounds
            return float(b.left), float(b.bottom), float(b.right), float(b.top)

    table = df if df is not None else _load_feature_table(city_key)
    pad = 0.001
    return (
        float(table["lon"].min()) - pad,
        float(table["lat"].min()) - pad,
        float(table["lon"].max()) + pad,
        float(table["lat"].max()) + pad,
    )


def _thermal_kelvin_array(city_key: str, df: pd.DataFrame) -> np.ndarray:
    """Kelvin LST from raw Landsat export or pipeline rasters (fallback PNG overlay)."""
    out_dir = _city_out_dir(city_key)
    raw_k = out_dir / "raw" / "landsat_lst_raw.tif"
    if raw_k.exists():
        return _read_raster(raw_k)

    raster_dir = out_dir / "rasters"
    for name in ("landsat_lst_c.tif", "lst_10m.tif"):
        path = raster_dir / name
        if path.exists():
            return _read_raster(path) + 273.15

    col = "lst_calibrated_c" if "lst_calibrated_c" in df.columns else "lst_c"
    return _grid_from_column(df, col) + 273.15


def _layer_array(city_key: str, layer: str, df: pd.DataFrame) -> np.ndarray:
    raster_dir = _city_out_dir(city_key) / "rasters"
    h = int(df["row"].max()) + 1
    w = int(df["col"].max()) + 1

    if layer == "thermal":
        return _thermal_kelvin_array(city_key, df)

    raster_layers = {
        "lst": "lst_10m.tif",
        "ndvi": "ndvi.tif",
    }
    if layer in raster_layers:
        try:
            return _read_raster(raster_dir / raster_layers[layer])
        except FileNotFoundError:
            if layer == "lst":
                col = "lst_calibrated_c" if "lst_calibrated_c" in df.columns else "lst_c"
            else:
                col = "ndvi"
            return _grid_from_column(df, col)

    if layer == "utci":
        try:
            lst = _read_raster(raster_dir / "lst_10m.tif")
        except FileNotFoundError:
            lst_col = "lst_calibrated_c" if "lst_calibrated_c" in df.columns else "lst_c"
            lst = _grid_from_column(df, lst_col)
        humidity = float(df.get("humidity_proxy", pd.Series([0.55])).mean())
        return lst * 0.72 + humidity * 8.0 - 2.5

    if layer == "svf":
        for name in ("impervious_frac.tif", "ndbi.tif"):
            try:
                return _read_raster(raster_dir / name)
            except FileNotFoundError:
                continue
        col = "impervious_frac" if "impervious_frac" in df.columns else "ndbi"
        return _grid_from_column(df, col)

    if layer == "vulnerability":
        return _grid_from_column(df, "hotspot_class")

    if layer == "ghsl_built":
        for name in ("ghsl_built_surface.tif", "impervious_frac.tif"):
            try:
                raw = _read_raster(raster_dir / name)
                if name.startswith("ghsl"):
                    return _normalize_built_surface(raw)
                return raw
            except FileNotFoundError:
                continue
        col = "building_density" if "building_density" in df.columns else "impervious_frac"
        return _grid_from_column(df, col)

    if layer == "ghsl_population":
        try:
            return _read_raster(raster_dir / "ghsl_population.tif")
        except FileNotFoundError:
            if "population" in df.columns:
                return _grid_from_column(df, "population")
            raise

    if layer == "ghsl_smod":
        try:
            smod = _read_raster(raster_dir / "ghsl_smod.tif")
            return np.clip(smod / 30.0, 0, 1).astype(np.float32)
        except FileNotFoundError:
            if "lcz_class" in df.columns:
                return np.clip(_grid_from_column(df, "lcz_class") / 10.0, 0, 1)
            if "building_density" in df.columns:
                return _grid_from_column(df, "building_density")
            raise

    try:
        return _read_raster(raster_dir / "lst_10m.tif")
    except FileNotFoundError:
        lst_col = "lst_calibrated_c" if "lst_calibrated_c" in df.columns else "lst_c"
        return _grid_from_column(df, lst_col)


def _colormap_for_layer(layer: str):
    if layer == "thermal":
        return "jet"
    if layer == "ndvi":
        return "YlGn"
    if layer == "svf":
        return "Purples"
    if layer == "ghsl_built":
        return "Oranges"
    if layer == "ghsl_population":
        return "YlOrRd"
    if layer == "ghsl_smod":
        return "BuPu"
    if layer == "vulnerability":
        return "RdYlGn_r"
    return "RdYlBu_r"


@lru_cache(maxsize=64)
def get_heatmap_meta(city_key: str, layer: str = "lst") -> dict[str, Any]:
    df = _load_feature_table(city_key)
    arr = _layer_array(city_key, layer, df)

    if layer == "thermal":
        land = land_visible_mask(df, arr.shape)
        valid = arr[land & np.isfinite(arr)]
    else:
        valid = arr[np.isfinite(arr)]

    vmin = float(np.percentile(valid, 2)) if valid.size else 0.0
    vmax = float(np.percentile(valid, 98)) if valid.size else 1.0
    left, bottom, right, top = _raster_bounds(city_key, df)
    meta: dict[str, Any] = {
        "layer": layer,
        "bounds": [[bottom, left], [top, right]],
        "vmin": round(vmin, 2),
        "vmax": round(vmax, 2),
        "width": int(arr.shape[1]),
        "height": int(arr.shape[0]),
        "grid_step": DEFAULT_GRID_STEP,
    }
    if layer == "thermal":
        meta["unit"] = "K"
        meta["source"] = "Landsat 8 ST_B10"
        display_bbox = data_bbox_from_pixels(city_key)
        if display_bbox:
            meta["display_bounds"] = [
                [display_bbox[1], display_bbox[0]],
                [display_bbox[3], display_bbox[2]],
            ]
    elif layer == "ghsl_built":
        meta["unit"] = "built-up index"
        meta["source"] = "GHSL Built-S (Hugging Face cache)"
    elif layer == "ghsl_population":
        meta["unit"] = "people/cell"
        meta["source"] = "GHSL Population (Hugging Face cache)"
    elif layer == "ghsl_smod":
        meta["unit"] = "settlement degree"
        meta["source"] = "GHSL SMOD (Hugging Face cache)"

    raster_dir = _city_out_dir(city_key) / "rasters"
    has_ghsl_built = (raster_dir / "ghsl_built_surface.tif").exists() or "building_density" in df.columns
    has_ghsl_smod = (raster_dir / "ghsl_smod.tif").exists() or "lcz_class" in df.columns
    has_ghsl_pop = (raster_dir / "ghsl_population.tif").exists() or "population" in df.columns

    if layer == "ghsl_built" and not has_ghsl_built:
        meta["data_available"] = False
        meta["error"] = "Error fetching data: GHSL Built-S raster not found. Re-run pipeline with --data-mode local --force"
    elif layer == "ghsl_smod" and not has_ghsl_smod:
        meta["data_available"] = False
        meta["error"] = "Error fetching data: GHSL SMOD raster not found. Re-run pipeline with --data-mode local --force"
    elif layer == "ghsl_population" and not has_ghsl_pop:
        meta["data_available"] = False
        meta["error"] = "Error fetching data: GHSL population raster not found. Re-run pipeline with --data-mode local --force"
    else:
        meta["data_available"] = True
        if layer == "ghsl_built" and not (raster_dir / "ghsl_built_surface.tif").exists():
            meta["source"] = "GHSL Built-S (feature-table proxy from building density)"
        if layer == "ghsl_smod" and not (raster_dir / "ghsl_smod.tif").exists():
            meta["source"] = "GHSL SMOD (feature-table proxy from LCZ class)"
    return meta


def get_heatmap_png(city_key: str, layer: str = "lst") -> bytes:
    """Render continuous heatmap PNG from pipeline raster (UHI-Analysis style)."""
    out_dir = _city_out_dir(city_key)
    maps_dir = out_dir / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    cache = maps_dir / ("overlay_thermal_masked.png" if layer == "thermal" else f"overlay_{layer}.png")

    df = _load_feature_table(city_key)
    arr = _layer_array(city_key, layer, df)
    meta = get_heatmap_meta(city_key, layer)

    lst_tif = out_dir / "rasters" / "lst_10m.tif"
    parquet = out_dir / "tables" / "feature_table.parquet"
    source_mtime = lst_tif.stat().st_mtime if lst_tif.exists() else parquet.stat().st_mtime

    if cache.exists() and cache.stat().st_mtime > source_mtime:
        return cache.read_bytes()

    cmap = _colormap_for_layer(layer)
    norm_arr = np.flipud(arr)  # align PNG with geographic north-up for Leaflet

    if layer == "thermal":
        land = np.flipud(land_visible_mask(df, arr.shape))
        norm_arr = np.where(land, norm_arr, np.nan)

    fig = plt.figure(figsize=(norm_arr.shape[1] / 72, norm_arr.shape[0] / 72), dpi=72)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(
        norm_arr,
        cmap=cmap,
        vmin=meta["vmin"],
        vmax=meta["vmax"],
        interpolation="nearest" if layer == "thermal" else "bilinear",
        aspect="auto",
    )
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=(layer == "thermal"), pad_inches=0)
    plt.close(fig)
    png_bytes = buf.getvalue()
    cache.write_bytes(png_bytes)
    logger.info("Heatmap overlay cached: %s (%dx%d)", cache, arr.shape[1], arr.shape[0])
    return png_bytes


def build_fine_grid_geojson(
    city_key: str, step: int | None = None, mask_water: bool = True
) -> dict[str, Any]:
    """
    Pixel-aligned grid from pipeline feature table (10 m cells).
    step=1 → full resolution; larger step aggregates blocks.
    """
    cfg = load_city_config(ROOT / "configs" / "cities.yaml", city_key)
    df = _load_feature_table(city_key)
    raster_dir = _city_out_dir(city_key) / "rasters"
    ghsl_built_path = raster_dir / "ghsl_built_surface.tif"
    ghsl_smod_path = raster_dir / "ghsl_smod.tif"
    if ghsl_built_path.exists():
        built_raw = _read_raster(ghsl_built_path)
        built_norm = _normalize_built_surface(built_raw)
        df = df.copy()
        df["ghsl_built"] = built_norm[df["row"].to_numpy(), df["col"].to_numpy()]
    elif "building_density" in df.columns:
        df = df.copy()
        df["ghsl_built"] = df["building_density"].astype(np.float32)
    if ghsl_smod_path.exists():
        smod_raw = _read_raster(ghsl_smod_path)
        df = df.copy()
        df["ghsl_smod"] = smod_raw[df["row"].to_numpy(), df["col"].to_numpy()]
    elif "lcz_class" in df.columns:
        df = df.copy()
        df["ghsl_smod"] = df["lcz_class"].astype(np.float32)
    if mask_water:
        df = visible_pixels(df)
    h = int(df["row"].max()) + 1 if len(df) else 0
    w = int(df["col"].max()) + 1 if len(df) else 0

    if step is None:
        step = DEFAULT_GRID_STEP
    step = max(1, int(step))

    n_cells = (h // step) * (w // step) if h and w else 0
    if n_cells > MAX_GRID_FEATURES:
        step = max(step, int(np.ceil(np.sqrt((h * w) / MAX_GRID_FEATURES))))

    features: list[dict[str, Any]] = []

    lst_col = "lst_calibrated_c" if "lst_calibrated_c" in df.columns else "lst_c"
    grouped_df = df.assign(
        row_bin=(df["row"] // step) * step,
        col_bin=(df["col"] // step) * step,
        hotspot_flag=(df["hotspot_class"] >= 1).astype(float),
    )
    agg_kwargs: dict[str, Any] = {
        "lst_display": (lst_col, "mean"),
        "lst_sat": ("lst_c", "mean"),
        "ndvi": ("ndvi", "mean"),
        "ndbi": ("ndbi", "mean"),
        "hotspot_flag": ("hotspot_flag", "mean"),
        "hotspot_class": ("hotspot_class", "max"),
        "lon_min": ("lon", "min"),
        "lon_max": ("lon", "max"),
        "lat_min": ("lat", "min"),
        "lat_max": ("lat", "max"),
    }
    if "humidity_proxy" in grouped_df.columns:
        agg_kwargs["humidity_proxy"] = ("humidity_proxy", "mean")
    if "gi_star_z" in grouped_df.columns:
        agg_kwargs["gi_star_z"] = ("gi_star_z", "mean")
    if "impervious_frac" in grouped_df.columns:
        agg_kwargs["impervious_frac"] = ("impervious_frac", "mean")
    if "building_density" in grouped_df.columns:
        agg_kwargs["building_density"] = ("building_density", "mean")
    if "population" in grouped_df.columns:
        agg_kwargs["population"] = ("population", "mean")
    if "ghsl_built" in grouped_df.columns:
        agg_kwargs["ghsl_built"] = ("ghsl_built", "mean")
    if "ghsl_smod" in grouped_df.columns:
        agg_kwargs["ghsl_smod"] = ("ghsl_smod", "mean")
    if "is_water" in grouped_df.columns:
        agg_kwargs["is_water"] = ("is_water", "mean")

    blocks = grouped_df.groupby(["row_bin", "col_bin"], sort=False).agg(**agg_kwargs).reset_index()

    for block in blocks.itertuples(index=False):
        if mask_water and hasattr(block, "is_water") and float(block.is_water) > 0.5:
            continue

        r0 = int(block.row_bin)
        c0 = int(block.col_bin)

        avg_lst = float(np.nan_to_num(block.lst_display, nan=35.0))
        avg_raw = float(np.nan_to_num(block.lst_sat, nan=avg_lst))
        avg_ndvi = float(np.nan_to_num(block.ndvi, nan=0.3))
        avg_ndbi = float(np.nan_to_num(block.ndbi, nan=0.1))
        avg_imp = float(np.nan_to_num(getattr(block, "impervious_frac", np.nan), nan=np.nan))
        if not np.isfinite(avg_imp):
            avg_imp = float(np.clip(1.0 - avg_ndvi, 0.0, 1.0))
        avg_pop = float(np.nan_to_num(getattr(block, "population", np.nan), nan=0.0))
        avg_bld = float(np.nan_to_num(getattr(block, "building_density", np.nan), nan=np.nan))
        avg_ghsl_built = float(np.nan_to_num(getattr(block, "ghsl_built", np.nan), nan=np.nan))
        avg_ghsl_smod = float(np.nan_to_num(getattr(block, "ghsl_smod", np.nan), nan=np.nan))
        hotspot_frac = float(np.nan_to_num(block.hotspot_flag, nan=0.0))
        humidity = float(np.nan_to_num(getattr(block, "humidity_proxy", 0.55), nan=0.55))
        utci = float(np.nan_to_num(avg_lst * 0.72 + humidity * 8.0 - 2.5, nan=35.0))

        if avg_lst >= 42 or hotspot_frac > 0.35:
            vuln = "CRITICAL"
        elif avg_lst >= 40 or hotspot_frac > 0.2:
            vuln = "HIGH"
        elif avg_lst >= 38:
            vuln = "MODERATE"
        else:
            vuln = "LOW"

        w_min_lon = float(block.lon_min)
        w_max_lon = float(block.lon_max)
        w_min_lat = float(block.lat_min)
        w_max_lat = float(block.lat_max)
        centroid_lon = (w_min_lon + w_max_lon) / 2
        centroid_lat = (w_min_lat + w_max_lat) / 2
        area_name = _nearest_ward_name(cfg["city_name"], centroid_lon, centroid_lat, f"Cell {r0},{c0}")

        cell_id = f"{city_key}_r{r0}_c{c0}"
        polygon = [
            [w_min_lon, w_min_lat],
            [w_max_lon, w_min_lat],
            [w_max_lon, w_max_lat],
            [w_min_lon, w_max_lat],
            [w_min_lon, w_min_lat],
        ]

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [polygon]},
                "properties": {
                    "ward_id": cell_id,
                    "name": area_name,
                    "row": r0,
                    "col": c0,
                    "grid_step": step,
                    "avg_lst_c": round(np.nan_to_num(avg_raw, nan=35.0), 2),
                    "lst_calibrated_c": round(np.nan_to_num(avg_lst, nan=35.0), 2),
                    "simulated_lst_c": round(np.nan_to_num(avg_lst, nan=35.0), 2),
                    "heat_stress_utci_c": round(np.nan_to_num(utci, nan=35.0), 2),
                    "cooling_delta_c": 0.0,
                    "ndvi": round(np.nan_to_num(avg_ndvi, nan=0.3), 3),
                    "ndbi": round(np.nan_to_num(avg_ndbi, nan=0.1), 3),
                    "impervious_frac": round(np.nan_to_num(avg_imp, nan=0.5), 3),
                    "building_density": round(np.nan_to_num(avg_bld, nan=avg_imp), 3),
                    "population": round(np.nan_to_num(avg_pop, nan=0.0), 1),
                    "ghsl_built": round(
                        np.nan_to_num(
                            avg_ghsl_built if np.isfinite(avg_ghsl_built) else avg_bld,
                            nan=np.nan_to_num(avg_imp, nan=0.0),
                        ),
                        2,
                    ),
                    "ghsl_smod": round(
                        np.nan_to_num(avg_ghsl_smod, nan=0.0),
                        1,
                    ),
                    "vulnerability_class": vuln,
                    "hotspot_fraction": round(np.nan_to_num(hotspot_frac, nan=0.0), 3),
                    "hotspot_class": int(getattr(block, "hotspot_class", 0)),
                    "gi_star_z": round(float(np.nan_to_num(getattr(block, "gi_star_z", 0.0), nan=0.0)), 3),
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "grid_step": step,
            "rows": h,
            "cols": w,
            "cell_count": len(features),
            "mask_water": mask_water,
            "resolution_m": cfg.get("target_resolution_m", 10) * step,
        },
    }


def build_sample_points_geojson(city_key: str, stride: int = 4, mask_water: bool = True) -> dict[str, Any]:
    """Colored sample points for UHI-Analysis-style dot overlay."""
    df = _load_feature_table(city_key)
    if mask_water:
        df = visible_pixels(df)
    h = int(df["row"].max()) + 1
    w = int(df["col"].max()) + 1
    stride = max(1, stride)
    stride = max(stride, int(np.ceil(np.sqrt(len(df) / MAX_SAMPLE_POINTS))))

    sampled = df[(df["row"] % stride == 0) & (df["col"] % stride == 0)]
    p33 = float(df["lst_c"].quantile(0.33))
    p66 = float(df["lst_c"].quantile(0.66))

    features = []
    for _, row in sampled.iterrows():
        lst = float(row["lst_c"])
        if lst >= p66:
            zone = "Hot Zone"
        elif lst >= p33:
            zone = "Mild Zone"
        else:
            zone = "Cool Zone"

        cluster = "normal"
        gi = float(row.get("gi_star_z", 0) or 0)
        hs = int(row.get("hotspot_class", 0))
        if hs >= 2 and gi > 0:
            cluster = "hot_spot"
        elif gi < -1.5:
            cluster = "cold_spot"

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
                "properties": {
                    "lst_c": round(lst, 2),
                    "zone": zone,
                    "cluster": cluster,
                    "hotspot_class": hs,
                    "ndvi": round(float(row["ndvi"]), 3),
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "stride": stride,
            "point_count": len(features),
            "grid_size": f"{h}x{w}",
            "max_points": MAX_SAMPLE_POINTS,
        },
    }
