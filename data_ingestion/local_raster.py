"""Clip and resample local GeoTIFF sources to city bbox grid."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds as window_from_bounds

logger = logging.getLogger(__name__)


def clip_raster_to_bbox(
    src_path: Path,
    bbox: list[float],
    target_shape: tuple[int, int] | None = None,
    resampling: Resampling = Resampling.bilinear,
) -> np.ndarray:
    """Read a GeoTIFF, clip to WGS84 bbox, optionally resample to target (h, w)."""
    src_path = Path(src_path)
    if not src_path.exists():
        raise FileNotFoundError(f"Raster not found: {src_path}")

    min_lon, min_lat, max_lon, max_lat = bbox
    with rasterio.open(src_path) as src:
        src_crs = src.crs or "EPSG:4326"
        clip_bounds = transform_bounds("EPSG:4326", src_crs, min_lon, min_lat, max_lon, max_lat)
        window = window_from_bounds(*clip_bounds, transform=src.transform)
        window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        if window.width <= 0 or window.height <= 0:
            raise ValueError(f"Source raster {src_path.name} does not overlap city bbox")

        data = src.read(1, window=window, boundless=True, fill_value=src.nodata or 0)
        src_transform = src.window_transform(window)
        src_nodata = src.nodata

        if target_shape is None:
            return np.where(data == src_nodata, np.nan, data).astype(np.float32) if src_nodata is not None else data.astype(np.float32)

        h, w = target_shape
        dst = np.full((h, w), np.nan, dtype=np.float32)
        dst_transform = from_bounds(min_lon, min_lat, max_lon, max_lat, w, h)
        reproject(
            source=data,
            destination=dst,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:4326",
            src_nodata=src_nodata,
            dst_nodata=np.nan,
            resampling=resampling,
        )
        return np.nan_to_num(dst, nan=0.0).astype(np.float32)
