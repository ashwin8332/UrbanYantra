"""Data ingestion layer — GEE + local cache."""

from __future__ import annotations

import logging
from pathlib import Path

from data_ingestion.era5_land import ingest_era5_land
from data_ingestion.benchmark_datasets import export_benchmark_summaries
from data_ingestion.ghsl import ingest_ghsl
from data_ingestion.landsat_lst import ingest_landsat_lst
from data_ingestion.osm_morphology import fetch_osm_morphology
from data_ingestion.sentinel2 import ingest_sentinel2_indices
from data_ingestion.worldcover import ingest_worldcover

logger = logging.getLogger(__name__)


def run_ingestion(config: dict) -> dict:
    out_dir = Path(config["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== Data ingestion: %s ===", config.get("city_name", "city"))
    artifacts = {
        "landsat_lst": ingest_landsat_lst(config, out_dir),
        "sentinel2_indices": ingest_sentinel2_indices(config, out_dir),
        "worldcover": ingest_worldcover(config, out_dir),
        "ghsl": ingest_ghsl(config, out_dir),
        "era5_land": ingest_era5_land(config, out_dir),
        # After Sentinel-2 / WorldCover so morphology matches the satellite grid
        "osm_morphology": fetch_osm_morphology(config, out_dir),
        "benchmarks": export_benchmark_summaries(config, out_dir),
    }
    logger.info("Ingestion complete.")
    return artifacts
