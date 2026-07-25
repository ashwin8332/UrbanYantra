"""Land / city-boundary masks for satellite thermal overlays (all cities)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from shapely.geometry import mapping

from features.display_pixels import visible_pixels
from utils import load_city_config

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]


def _city_out_dir(city_key: str) -> Path:
    cfg = load_city_config(ROOT / "configs" / "cities.yaml", city_key)
    return ROOT / cfg["output_dir"]


def _load_feature_table(city_key: str) -> pd.DataFrame:
    return pd.read_parquet(_city_out_dir(city_key) / "tables" / "feature_table.parquet")


def data_bbox_from_pixels(city_key: str) -> list[float] | None:
    """Extent of visible land pixels — matches map summary bbox."""
    try:
        df = _load_feature_table(city_key)
        vis = visible_pixels(df)
        if vis.empty:
            vis = df
        pad = 0.002
        return [
            float(vis["lon"].min()) - pad,
            float(vis["lat"].min()) - pad,
            float(vis["lon"].max()) + pad,
            float(vis["lat"].max()) + pad,
        ]
    except FileNotFoundError:
        return None


def land_visible_mask(df: pd.DataFrame, shape: tuple[int, int]) -> np.ndarray:
    """True where pipeline marks land / urban pixels (excludes sea & rural fringe)."""
    h, w = shape
    mask = np.zeros((h, w), dtype=bool)
    if "is_excluded" in df.columns:
        vis = df[~df["is_excluded"]]
    else:
        vis = visible_pixels(df)
    for row in vis.itertuples(index=False):
        mask[int(row.row), int(row.col)] = True
    return mask


def resolve_city_boundary_geometry(city_key: str, config: dict | None = None):
    """OSM city / district polygon when cached or fetchable."""
    from data_ingestion.osm_city_boundary import (
        fetch_city_boundary_geometry,
        ingest_city_boundary,
        load_city_boundary_geometry,
    )

    if config is None:
        config = load_city_config(ROOT / "configs" / "cities.yaml", city_key)

    out_dir = _city_out_dir(city_key)
    geom = load_city_boundary_geometry(out_dir)
    if geom is not None:
        return geom

    try:
        df = _load_feature_table(city_key)
    except FileNotFoundError:
        return None

    geom = fetch_city_boundary_geometry(config, df=df)
    if geom is not None:
        try:
            ingest_city_boundary(config, out_dir, df=df, geom=geom)
        except Exception as exc:
            logger.warning("Could not cache city boundary for %s: %s", city_key, exc)
    return geom


def ee_clip_geometry(city_key: str, config: dict):
    """Earth Engine geometry: OSM city outline when available, else study bbox."""
    import ee

    from data_ingestion.gee_client import get_study_region

    geom = resolve_city_boundary_geometry(city_key, config)
    if geom is not None and not geom.is_empty:
        return ee.Geometry(mapping(geom))
    return get_study_region(config["bbox"])


def apply_gee_land_mask(image: Any, region: Any) -> Any:
    """Mask permanent water (WorldCover + JRC) so ocean is transparent on thermal tiles."""
    import ee

    wc = (
        ee.ImageCollection("ESA/WorldCover/v200")
        .filterDate("2021-01-01", "2021-12-31")
        .first()
        .select("Map")
    )
    not_water_wc = wc.neq(80)

    jrc = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").lt(50)
    land = not_water_wc.And(jrc)

    return image.updateMask(land).clip(region)
