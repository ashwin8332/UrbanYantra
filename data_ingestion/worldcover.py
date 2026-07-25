"""ESA WorldCover 10 m land use / land cover."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio

from data_ingestion.cache import save_geotiff
from data_ingestion.gee_client import get_study_region, init_gee
from data_ingestion.data_provenance import is_real_data_mode, require_real_source, use_gee_for_satellite
from utils import grid_shape_from_bbox, synthetic_grid_shape

logger = logging.getLogger(__name__)

# ESA WorldCover class codes (simplified)
IMPERVIOUS_CLASSES = {50, 60, 80}  # built-up, bare, water edge handled separately
VEGETATION_CLASSES = {10, 20, 30, 40, 90, 95, 100}
WATER_CLASS = 80


def generate_synthetic_lulc(shape: tuple[int, int] = (120, 120)) -> np.ndarray:
    h, w = shape
    y, x = np.mgrid[0:h, 0:w]
    urban = ((x - w * 0.55) ** 2 + (y - h * 0.45) ** 2) < 25**2
    lulc = np.full((h, w), 30, dtype=np.uint8)  # grassland default
    lulc[urban] = 50  # built-up
    lulc[y < h * 0.15] = 10  # tree cover north
    lulc[(x > w * 0.8) & (y > h * 0.7)] = 80  # water pocket
    return lulc


def ingest_worldcover(config: dict, out_dir: Path) -> Path:
    out_path = out_dir / "rasters" / "worldcover.tif"
    expected_shape = (
        synthetic_grid_shape(config)
        if config.get("data_mode", "synthetic") == "synthetic"
        else grid_shape_from_bbox(config["bbox"], config.get("target_resolution_m", 10))
    )
    if out_path.exists() and not config.get("force_refresh"):
        with rasterio.open(out_path) as src:
            if (src.height, src.width) == expected_shape:
                return out_path
        logger.warning("Cached worldcover.tif shape mismatch — regenerating for %s.", config.get("city_name"))
        out_path.unlink(missing_ok=True)

    mode = config.get("data_mode", "synthetic")
    if use_gee_for_satellite(config):
        try:
            import ee
            import requests

            if not init_gee(config=config):
                raise RuntimeError("GEE not available")
            wc = (
                ee.ImageCollection(config["worldcover"]["collection"])
                .filterDate(f"{config['worldcover']['year']}-01-01", f"{config['worldcover']['year']}-12-31")
                .first()
                .select("Map")
                .clip(get_study_region(config["bbox"]))
            )
            export_scale = max(int(config.get("target_resolution_m", 10)), 10)
            url = wc.getDownloadURL(
                {
                    "scale": export_scale,
                    "crs": config.get("crs", "EPSG:4326"),
                    "region": get_study_region(config["bbox"]),
                    "format": "GEO_TIFF",
                }
            )
            resp = requests.get(url, timeout=300)
            resp.raise_for_status()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(resp.content)
            return out_path
        except Exception as exc:
            require_real_source(config, "ESA WorldCover", exc)

    if is_real_data_mode(config):
        raise RuntimeError(f"WorldCover unavailable (data_mode={mode})")

    lulc = generate_synthetic_lulc(synthetic_grid_shape(config))
    save_geotiff(lulc.astype(np.float32), out_path, config["bbox"], nodata=0)
    return out_path
