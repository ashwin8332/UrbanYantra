"""Helpers for GEE getDownloadURL — safe scale + multi-band GeoTIFF export."""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import rasterio
import requests

logger = logging.getLogger(__name__)

# GEE getPixels ~50 MB / side-length cap — stay conservative
MAX_EXPORT_SIDE_PX = 4096


def compute_gee_export_scale(bbox: list[float], min_scale_m: float = 30, max_scale_m: float = 500) -> int:
    """Pick ground scale (m) so export grid stays within GEE pixel limits."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_mid = (min_lat + max_lat) / 2.0
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat_mid))
    width_m = max(1.0, (max_lon - min_lon) * m_per_deg_lon)
    height_m = max(1.0, (max_lat - min_lat) * m_per_deg_lat)
    scale = float(min_scale_m)
    while max(width_m / scale, height_m / scale) > MAX_EXPORT_SIDE_PX and scale < max_scale_m:
        scale *= 1.25
    chosen = int(math.ceil(scale))
    logger.info(
        "GEE export scale=%dm for bbox (%.2f°×%.2f° ≈ %.0f×%.0f m)",
        chosen,
        max_lon - min_lon,
        max_lat - min_lat,
        width_m,
        height_m,
    )
    return chosen


def download_gee_image(
    image,
    band_names: list[str],
    region,
    bbox: list[float],
    out_path: Path,
    config: dict,
    scale: int | None = None,
) -> Path:
    """Download ee.Image bands as one GeoTIFF via getDownloadURL."""
    scale = scale or compute_gee_export_scale(bbox)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    url = image.select(band_names).getDownloadURL(
        {
            "scale": scale,
            "crs": config.get("crs", "EPSG:4326"),
            "region": region,
            "format": "GEO_TIFF",
        }
    )
    resp = requests.get(url, timeout=600)
    if not resp.ok:
        snippet = (resp.text or "")[:400]
        raise RuntimeError(f"GEE export failed HTTP {resp.status_code} scale={scale}m bands={band_names}: {snippet}")
    out_path.write_bytes(resp.content)
    return out_path


def read_bands_from_geotiff(path: Path, band_map: dict[str, int]) -> dict[str, np.ndarray]:
    """Read selected 1-based band indices from a multi-band GeoTIFF."""
    out: dict[str, np.ndarray] = {}
    with rasterio.open(path) as src:
        for name, idx in band_map.items():
            out[name] = src.read(idx).astype(np.float32)
    return out
