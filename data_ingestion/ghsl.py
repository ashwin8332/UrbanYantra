"""GHSL building height and population layers."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from data_ingestion.cache import save_geotiff
from data_ingestion.data_provenance import is_local_data_mode, is_real_data_mode, prefer_local_files, require_real_source
from utils import synthetic_grid_shape

logger = logging.getLogger(__name__)


def generate_synthetic_ghsl(shape: tuple[int, int] = (120, 120)) -> tuple[np.ndarray, np.ndarray]:
    h, w = shape
    y, x = np.mgrid[0:h, 0:w]
    urban = np.exp(-((x - w * 0.55) ** 2 + (y - h * 0.45) ** 2) / (2 * 18**2))
    height = (5 + 25 * urban + np.random.default_rng(3).normal(0, 1, (h, w))).clip(0, 40)
    pop = (500 + 15000 * urban).astype(np.float32)
    return height.astype(np.float32), pop


def ingest_ghsl(config: dict, out_dir: Path) -> dict[str, Path]:
    paths = {
        "building_height": out_dir / "rasters" / "ghsl_building_height.tif",
        "population": out_dir / "rasters" / "ghsl_population.tif",
    }
    if all(p.exists() for p in paths.values()) and not config.get("force_refresh"):
        return paths

    if is_local_data_mode(config) or prefer_local_files(config):
        try:
            from data_ingestion.ghsl_local import ingest_ghsl_local

            return ingest_ghsl_local(config, out_dir)
        except FileNotFoundError as exc:
            if is_local_data_mode(config):
                raise
            logger.warning("Local/Hugging Face GHSL not available (%s) — trying GEE.", exc)

    mode = config.get("data_mode", "synthetic")
    if mode == "gee":
        try:
            import ee
            import requests

            from data_ingestion.gee_client import get_study_region, init_gee

            if not init_gee(config=config):
                raise RuntimeError("GEE not available")
            region = get_study_region(config["bbox"])
            scale = config.get("target_resolution_m", 10) * 10  # GHSL ~100 m native
            for key, coll_id in [
                ("building_height", config["ghsl"]["building_height"]),
                ("population", config["ghsl"]["population"]),
            ]:
                img = ee.Image(coll_id).clip(region)
                url = img.getDownloadURL(
                    {"scale": scale, "crs": config.get("crs", "EPSG:4326"), "region": region, "format": "GEO_TIFF"}
                )
                resp = requests.get(url, timeout=300)
                resp.raise_for_status()
                paths[key].parent.mkdir(parents=True, exist_ok=True)
                paths[key].write_bytes(resp.content)
            return paths
        except Exception as exc:
            require_real_source(config, "GHSL", exc)

    if is_real_data_mode(config):
        raise RuntimeError("GHSL unavailable in gee mode")

    height, pop = generate_synthetic_ghsl(synthetic_grid_shape(config))
    save_geotiff(height, paths["building_height"], config["bbox"])
    save_geotiff(pop, paths["population"], config["bbox"])
    return paths
