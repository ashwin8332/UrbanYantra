"""Sentinel-2 surface reflectance and spectral indices via GEE (+ Landsat SR fallback)."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from data_ingestion.cache import save_geotiff
from data_ingestion.data_provenance import is_real_data_mode, require_real_source, use_gee_for_satellite
from data_ingestion.gee_client import get_study_region, init_gee
from data_ingestion.gee_export import compute_gee_export_scale, download_gee_image, read_bands_from_geotiff
from features.spectral_indices import compute_indices_from_bands
from utils import synthetic_grid_shape

logger = logging.getLogger(__name__)

S2_BANDS = ["B2", "B3", "B4", "B8", "B11"]


def generate_synthetic_s2_bands(config: dict, shape: tuple[int, int] = (120, 120)) -> dict[str, np.ndarray]:
    """Synthetic Sentinel-2-like bands for fallback."""
    rng = np.random.default_rng(7)
    h, w = shape
    y, x = np.mgrid[0:h, 0:w]
    urban = np.exp(-((x - w * 0.55) ** 2 + (y - h * 0.45) ** 2) / (2 * 20**2))
    green = (0.15 + 0.25 * (1 - urban) + rng.normal(0, 0.02, (h, w))).clip(0.01, 0.5)
    nir = (0.2 + 0.35 * (1 - urban) + rng.normal(0, 0.02, (h, w))).clip(0.05, 0.7)
    swir = (0.1 + 0.2 * urban + rng.normal(0, 0.02, (h, w))).clip(0.02, 0.5)
    blue = (0.05 + 0.05 * urban + rng.normal(0, 0.01, (h, w))).clip(0.01, 0.2)
    return {"B2": blue.astype(np.float32), "B3": green.astype(np.float32), "B4": green * 0.9, "B8": nir, "B11": swir}


def _summer_filter(collection, config: dict):
    """Restrict to clear-sky summer months (matches Landsat LST window)."""
    months = config.get("date_range", {}).get("lst_months")
    if not months:
        return collection
    import ee

    filters = [ee.Filter.calendarRange(int(m), int(m), "month") for m in months]
    return collection.filter(ee.Filter.Or(filters))


def fetch_sentinel2_gee(config: dict, out_dir: Path) -> dict[str, np.ndarray]:
    """Fetch S2 median composite as band arrays (single multi-band GeoTIFF export)."""
    import ee

    if not init_gee(config=config):
        raise RuntimeError("GEE not available")

    bbox = config["bbox"]
    region = get_study_region(bbox)
    s2_cfg = config["sentinel2"]
    scale = compute_gee_export_scale(bbox)

    def mask_clouds(img):
        qa = img.select("QA60")
        mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
        return img.updateMask(mask).divide(10000).copyProperties(img, ["system:time_start"])

    collection = (
        ee.ImageCollection(s2_cfg["collection"])
        .filterBounds(region)
        .filterDate(config["date_range"]["start"], config["date_range"]["end"])
    )
    collection = _summer_filter(collection, config)
    collection = collection.map(mask_clouds)
    count = collection.size().getInfo()
    if count == 0:
        logger.warning("S2 collection empty with cloud mask — retrying without QA mask")
        collection = (
            ee.ImageCollection(s2_cfg["collection"])
            .filterBounds(region)
            .filterDate(config["date_range"]["start"], config["date_range"]["end"])
        )
        collection = _summer_filter(collection, config)
        collection = collection.map(lambda img: img.divide(10000).copyProperties(img, ["system:time_start"]))
        count = collection.size().getInfo()
    if count == 0:
        raise ValueError("No Sentinel-2 scenes for bbox/date range")

    logger.info("Sentinel-2 scenes in composite: %d", count)
    composite = collection.median().clip(region)

    out_tif = out_dir / "rasters" / "s2_composite.tif"
    download_gee_image(composite, S2_BANDS, region, bbox, out_tif, config, scale=scale)
    band_map = {b: i + 1 for i, b in enumerate(S2_BANDS)}
    return read_bands_from_geotiff(out_tif, band_map)


def fetch_landsat_sr_bands_gee(config: dict, out_dir: Path) -> dict[str, np.ndarray]:
    """Fallback: Landsat 8 C2 L2 surface reflectance → S2-compatible band names."""
    import ee

    if not init_gee(config=config):
        raise RuntimeError("GEE not available")

    bbox = config["bbox"]
    region = get_study_region(bbox)
    ls_cfg = config["landsat"]
    scale = compute_gee_export_scale(bbox)

    collection = (
        ee.ImageCollection(ls_cfg["collection"])
        .filterBounds(region)
        .filterDate(config["date_range"]["start"], config["date_range"]["end"])
        .filter(ee.Filter.lt("CLOUD_COVER", ls_cfg.get("cloud_cover_max", 30)))
    )
    collection = _summer_filter(collection, config)

    def prep_sr(img):
        sr = img.select(["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6"]).multiply(0.0000275).add(-0.2)
        return sr.clamp(0, 1).rename(["B2", "B3", "B4", "B8", "B11"])

    count = collection.size().getInfo()
    if count == 0:
        raise ValueError("No Landsat SR scenes for fallback")
    logger.info("Landsat SR fallback — %d scenes", count)
    composite = collection.map(prep_sr).median().clip(region)

    out_tif = out_dir / "rasters" / "landsat_sr_composite.tif"
    download_gee_image(composite, ["B2", "B3", "B4", "B8", "B11"], region, bbox, out_tif, config, scale=scale)
    band_map = {b: i + 1 for i, b in enumerate(["B2", "B3", "B4", "B8", "B11"])}
    return read_bands_from_geotiff(out_tif, band_map)


def ingest_sentinel2_indices(config: dict, out_dir: Path) -> dict[str, Path]:
    """Ingest S2 (or Landsat SR fallback) and export NDVI, NDBI, NDWI, UTFVI rasters."""
    raster_dir = out_dir / "rasters"
    raster_dir.mkdir(parents=True, exist_ok=True)
    index_names = ["ndvi", "ndbi", "ndwi", "utfvi"]
    existing = {n: raster_dir / f"{n}.tif" for n in index_names}
    if all(p.exists() for p in existing.values()) and not config.get("force_refresh"):
        return existing

    bands = None
    if use_gee_for_satellite(config):
        try:
            bands = fetch_sentinel2_gee(config, out_dir)
        except Exception as exc:
            logger.warning("Sentinel-2 GEE export failed (%s) — trying Landsat SR fallback", exc)
            try:
                bands = fetch_landsat_sr_bands_gee(config, out_dir)
            except Exception as exc2:
                require_real_source(config, "Sentinel-2 / Landsat SR", exc2)

    if is_real_data_mode(config) and bands is None:
        raise RuntimeError(f"Spectral indices unavailable (data_mode={config.get('data_mode')})")

    if bands is None:
        bands = generate_synthetic_s2_bands(config, shape=synthetic_grid_shape(config))

    indices = compute_indices_from_bands(bands)
    paths = {}
    for name, arr in indices.items():
        p = raster_dir / f"{name}.tif"
        save_geotiff(arr, p, config["bbox"])
        paths[name] = p
    return paths
