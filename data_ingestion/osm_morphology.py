"""OpenStreetMap morphology — real building/road densities rasterized to the satellite grid."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from rasterio import features

from data_ingestion.cache import save_parquet
from data_ingestion.data_provenance import is_real_data_mode, require_real_source
from features.morphology import impervious_fraction
from utils import grid_shape_from_bbox, synthetic_grid_shape

logger = logging.getLogger(__name__)


def _pipeline_grid_shape(config: dict) -> tuple[int, int]:
    if config.get("data_mode", "synthetic") == "synthetic":
        return synthetic_grid_shape(config)
    return grid_shape_from_bbox(config["bbox"], config.get("target_resolution_m", 10))


def _grid_transform(bbox: list[float], h: int, w: int) -> Affine:
    min_lon, min_lat, max_lon, max_lat = bbox
    return Affine.translation(min_lon, max_lat) * Affine.scale(
        (max_lon - min_lon) / w,
        -(max_lat - min_lat) / h,
    )


def _reference_grid(config: dict, out_dir: Path) -> tuple[int, int]:
    for name in ("ndvi.tif", "landsat_lst_c.tif", "worldcover.tif"):
        path = out_dir / "rasters" / name
        if path.exists():
            with rasterio.open(path) as src:
                return src.height, src.width
    return _pipeline_grid_shape(config)


def _rasterize_polygons(geoms, transform: Affine, h: int, w: int) -> np.ndarray:
    shapes = [(geom, 1) for geom in geoms if geom is not None and not geom.is_empty]
    if not shapes:
        return np.zeros((h, w), dtype=np.float32)
    return features.rasterize(
        shapes,
        out_shape=(h, w),
        transform=transform,
        fill=0,
        dtype=np.float32,
        all_touched=True,
    )


def _rasterize_lines(geoms, transform: Affine, h: int, w: int) -> np.ndarray:
    shapes = [(geom, 1) for geom in geoms if geom is not None and not geom.is_empty]
    if not shapes:
        return np.zeros((h, w), dtype=np.float32)
    return features.rasterize(
        shapes,
        out_shape=(h, w),
        transform=transform,
        fill=0,
        dtype=np.float32,
        all_touched=True,
    )


def _smooth_density(arr: np.ndarray, size: int = 3) -> np.ndarray:
    from scipy.ndimage import uniform_filter

    out = uniform_filter(arr.astype(np.float64), size=size)
    mx = float(out.max()) or 1.0
    return np.clip(out / mx, 0, 1).astype(np.float32)


def _worldcover_morphology_fallback(config: dict, out_dir: Path, h: int, w: int) -> pd.DataFrame:
    """ESA WorldCover impervious proxy (real land-cover, not RNG)."""
    lulc_path = out_dir / "rasters" / "worldcover.tif"
    if not lulc_path.exists():
        raise FileNotFoundError(f"WorldCover raster missing: {lulc_path}")
    with rasterio.open(lulc_path) as src:
        lulc = src.read(1)
    if lulc.shape != (h, w):
        from scipy.ndimage import zoom

        zy = h / lulc.shape[0]
        zx = w / lulc.shape[1]
        lulc = zoom(lulc, (zy, zx), order=0)
    imp = impervious_fraction(lulc.astype(np.int32))
    road = (imp * 0.85).astype(np.float32)
    rows, cols = np.mgrid[0:h, 0:w]
    logger.info("OSM morphology fallback: ESA WorldCover impervious fraction")
    return pd.DataFrame(
        {
            "row": rows.ravel(),
            "col": cols.ravel(),
            "building_density": imp.ravel(),
            "road_density": road.ravel(),
        }
    )


def _osm_to_density_table(config: dict, out_dir: Path) -> pd.DataFrame:
    import osmnx as ox
    from shapely.geometry import box

    from data_ingestion.cache import save_geopackage

    bbox = config["bbox"]
    h, w = _reference_grid(config, out_dir)
    transform = _grid_transform(bbox, h, w)
    poly = box(bbox[0], bbox[1], bbox[2], bbox[3])
    ox.settings.use_cache = True
    ox.settings.log_console = False

    buildings = ox.features_from_polygon(poly, tags={"building": True})
    graph = ox.graph_from_polygon(poly, network_type="drive")
    edges = ox.graph_to_gdfs(graph, nodes=False)

    gpkg_path = out_dir / "vectors" / "osm_buildings.gpkg"
    save_geopackage(buildings[["geometry"]], gpkg_path, layer="buildings")
    logger.info("OSM buildings saved to %s (%d features)", gpkg_path, len(buildings))

    bldg_arr = _smooth_density(
        _rasterize_polygons(buildings.geometry, transform, h, w)
    )
    road_arr = _smooth_density(
        _rasterize_lines(edges.geometry, transform, h, w)
    )

    rows, cols = np.mgrid[0:h, 0:w]
    return pd.DataFrame(
        {
            "row": rows.ravel(),
            "col": cols.ravel(),
            "building_density": bldg_arr.ravel(),
            "road_density": road_arr.ravel(),
        }
    )


def fetch_osm_morphology(config: dict, out_dir: Path) -> Path:
    """Download OSM buildings/roads and rasterize density per grid cell."""
    out_path = out_dir / "tables" / "osm_morphology.parquet"
    if out_path.exists() and not config.get("force_refresh"):
        return out_path

    if is_real_data_mode(config):
        try:
            df = _osm_to_density_table(config, out_dir)
        except Exception as exc:
            logger.warning("OSM rasterization failed (%s) — using WorldCover impervious proxy.", exc)
            try:
                h, w = _reference_grid(config, out_dir)
                df = _worldcover_morphology_fallback(config, out_dir, h, w)
            except Exception as fallback_exc:
                require_real_source(config, "OSM morphology", fallback_exc)
                raise
    else:
        df = _synthetic_morphology(config)

    save_parquet(df, out_path)
    logger.info("Morphology table saved to %s (%d cells)", out_path, len(df))
    return out_path


def _synthetic_morphology(config: dict) -> pd.DataFrame:
    """Synthetic morphology grid (data_mode=synthetic only)."""
    h, w = synthetic_grid_shape(config)
    rng = np.random.default_rng(11)
    y, x = np.mgrid[0:h, 0:w]
    urban = np.exp(-((x - w * 0.55) ** 2 + (y - h * 0.45) ** 2) / (2 * 22**2))
    flat = h * w
    return pd.DataFrame(
        {
            "row": y.ravel(),
            "col": x.ravel(),
            "building_density": (0.1 + 0.8 * urban.ravel() + rng.normal(0, 0.05, flat)).clip(0, 1),
            "road_density": (0.05 + 0.6 * urban.ravel() + rng.normal(0, 0.04, flat)).clip(0, 1),
        }
    )
