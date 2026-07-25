"""Local cache helpers for GeoTIFF / Parquet / GeoPackage exports."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_bounds

if TYPE_CHECKING:
    import geopandas as gpd


def save_geotiff(
    array: np.ndarray,
    path: Path,
    bbox: list[float],
    crs: str = "EPSG:4326",
    nodata: float | None = -9999.0,
) -> Path:
    """Save 2D array as GeoTIFF using WGS84 bbox [min_lon, min_lat, max_lon, max_lat]."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    min_lon, min_lat, max_lon, max_lat = bbox
    height, width = array.shape
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, width, height)
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": array.dtype,
        "crs": crs,
        "transform": transform,
        "compress": "lzw",
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype(profile["dtype"]), 1)
    return path


def load_geotiff(path: Path) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as src:
        data = src.read(1)
        meta = src.meta.copy()
        bounds = src.bounds
    return data, {"bounds": bounds, "meta": meta, "transform": meta["transform"]}


def save_parquet(df: pd.DataFrame, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def save_geopackage(gdf: "gpd.GeoDataFrame", path: Path, layer: str = "data") -> Path:
    import geopandas as gpd  # optional heavy dep

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, layer=layer, driver="GPKG")
    return path
