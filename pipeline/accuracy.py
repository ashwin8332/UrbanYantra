"""Post-processing: OSM wards, CPCB calibration, zonal stats."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from calibration.station_bias import apply_calibration, run_station_calibration
from data_ingestion.cache import save_parquet
from data_ingestion.osm_wards import ingest_ward_boundaries
from features.zonal_wards import build_ward_zonal_geojson

logger = logging.getLogger(__name__)


def run_accuracy_layer(config: dict, df: pd.DataFrame, out_dir: Path, city_key: str) -> pd.DataFrame:
    """Ward boundaries → station calibration → zonal ward GeoJSON."""
    logger.info("=== Accuracy layer: wards + CPCB calibration ===")
    calibration = run_station_calibration(config, df, out_dir)
    df = apply_calibration(df, calibration)
    save_parquet(df, out_dir / "tables" / "feature_table.parquet")
    ingest_ward_boundaries(config, out_dir, df=df)
    build_ward_zonal_geojson(config, df, out_dir, city_key)
    logger.info(
        "Calibration bias=%.2f°C; wards written to geojson/ward_zonal.geojson",
        calibration.get("bias_c", 0.0),
    )
    return df
