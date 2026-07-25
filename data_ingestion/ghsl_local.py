"""D-04 — Local GHSL Built-S, SMOD, optional Built-H GeoTIFF tiles."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling

from data_ingestion.cache import save_geotiff
from data_ingestion.local_raster import clip_raster_to_bbox
from utils import grid_shape_from_bbox

logger = logging.getLogger(__name__)


def _path(config: dict, key: str) -> Path | None:
    from data_ingestion.ghsl_drive import pick_ghsl_geotiff_for_bbox
    from data_ingestion.remote_cache import resolve_dataset

    remote = (config.get("remote_data") or {})
    urban_folder = remote.get("urban_dataset_folder") or {}
    if urban_folder.get("huggingface_repo_id") or urban_folder.get("hf_repo_id"):
        if key in ("ghsl_built_s", "ghsl_smod", "ghsl_built_h"):
            try:
                return pick_ghsl_geotiff_for_bbox(config, key, config["bbox"])
            except FileNotFoundError:
                logger.warning("GHSL Hugging Face pick failed for %s", key)

    path = resolve_dataset(config, key)
    return path if path and path.exists() else None


def _target_shape(config: dict) -> tuple[int, int]:
    out_dir = Path(config["output_dir"])
    ref_raster = out_dir / "rasters" / "ndvi.tif"
    if ref_raster.exists():
        with rasterio.open(ref_raster) as src:
            return int(src.height), int(src.width)

    max_side = None if config.get("data_mode") == "local" else 120
    return grid_shape_from_bbox(
        config["bbox"],
        config.get("target_resolution_m", 10),
        max_side=max_side,
    )


def ingest_ghsl_local(config: dict, out_dir: Path) -> dict[str, Path]:
    """
    Clip local GHSL rasters to city bbox.

    Uses Built-S (surface) + SMOD (settlement type). Built-H 2018 height is optional —
    temporal offset vs 2024 LST is acceptable for morphology features (hackathon narrative).
    """
    raster_dir = out_dir / "rasters"
    raster_dir.mkdir(parents=True, exist_ok=True)
    shape = _target_shape(config)
    bbox = config["bbox"]

    paths: dict[str, Path] = {
        "building_height": raster_dir / "ghsl_building_height.tif",
        "population": raster_dir / "ghsl_population.tif",
        "built_surface": raster_dir / "ghsl_built_surface.tif",
        "smod": raster_dir / "ghsl_smod.tif",
    }

    built_s = _path(config, "ghsl_built_s")
    smod = _path(config, "ghsl_smod")
    built_h = _path(config, "ghsl_built_h")
    pop = _path(config, "ghsl_population")

    if not built_s and not smod and not built_h:
        raise FileNotFoundError(
            "Set ghsl_built_s / ghsl_smod in configs/remote_datasets.yaml (urban_dataset_folder on Hugging Face)"
        )

    surf = None
    if built_s:
        surf = clip_raster_to_bbox(built_s, bbox, target_shape=shape)
        save_geotiff(surf, paths["built_surface"], bbox)
        logger.info("GHSL Built-S clipped → %s", paths["built_surface"])

    if smod:
        smod_arr = clip_raster_to_bbox(smod, bbox, target_shape=shape, resampling=Resampling.nearest)
        save_geotiff(smod_arr, paths["smod"], bbox)
        logger.info("GHSL SMOD clipped → %s", paths["smod"])

    if built_h:
        height = clip_raster_to_bbox(built_h, bbox, target_shape=shape)
        save_geotiff(height, paths["building_height"], bbox)
        logger.info("GHSL Built-H (local) → %s", paths["building_height"])
    elif surf is not None:
        surf_norm = np.clip(surf / (np.percentile(surf[surf > 0], 95) + 1e-6), 0, 1)
        height = (5 + 30 * surf_norm).astype(np.float32)
        save_geotiff(height, paths["building_height"], bbox)
        logger.info("Building height proxied from Built-S → %s", paths["building_height"])
    else:
        height = np.full(shape, 8.0, dtype=np.float32)
        save_geotiff(height, paths["building_height"], bbox)

    if pop:
        pop_arr = clip_raster_to_bbox(pop, bbox, target_shape=shape)
        save_geotiff(pop_arr, paths["population"], bbox)
    elif surf is not None:
        pop_arr = (500 + 8000 * (surf / (surf.max() + 1e-6))).astype(np.float32)
        save_geotiff(pop_arr, paths["population"], bbox)
    else:
        pop_arr = np.full(shape, 1000.0, dtype=np.float32)
        save_geotiff(pop_arr, paths["population"], bbox)

    return paths
