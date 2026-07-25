"""Live satellite thermal raster tiles via Google Earth Engine (Landsat 8 ST_B10)."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from data_ingestion.gee_client import init_gee
from utils import load_city_config

from backend.app.services.thermal_mask import (
    apply_gee_land_mask,
    data_bbox_from_pixels,
    ee_clip_geometry,
    resolve_city_boundary_geometry,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]

# Jet palette — matches ECOSTRESS notebook (blue=cool, red=hot)
THERMAL_PALETTE = [
    "00008f",
    "0000ff",
    "00ffff",
    "00ff00",
    "ffff00",
    "ff7f00",
    "ff0000",
]


def _build_landsat_lst_image(config: dict, region) -> Any:
    import ee

    ls_cfg = config["landsat"]
    scale_factor = ls_cfg["scale_factor"]
    offset = ls_cfg["offset"]

    collection = (
        ee.ImageCollection(ls_cfg["collection"])
        .filterBounds(region)
        .filterDate(config["date_range"]["start"], config["date_range"]["end"])
        .filter(ee.Filter.lt("CLOUD_COVER", ls_cfg["cloud_cover_max"]))
    )

    lst_months = config.get("date_range", {}).get("lst_months")
    if lst_months:
        month_filters = [ee.Filter.calendarRange(int(m), int(m), "month") for m in lst_months]
        collection = collection.filter(ee.Filter.Or(month_filters))

    def apply_scale(img):
        lst = img.select(ls_cfg["lst_band"]).multiply(scale_factor).add(offset)
        valid = lst.gt(200).And(lst.lt(400))
        return lst.updateMask(valid).rename("LST_K")

    lst_median = collection.map(apply_scale).median()
    lst_median = apply_gee_land_mask(lst_median, region)
    return lst_median.clip(region)


@lru_cache(maxsize=32)
def get_thermal_tiles(city_key: str) -> dict[str, Any]:
    """Return GEE map-tile URL and Kelvin scale for satellite thermal overlay."""
    config = load_city_config(ROOT / "configs" / "cities.yaml", city_key)
    if not init_gee(config=config):
        raise RuntimeError(
            "Google Earth Engine not available — run earthengine authenticate and set gee_project"
        )

    import ee

    region = ee_clip_geometry(city_key, config)
    lst_image = _build_landsat_lst_image(config, region)

    stats = lst_image.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=region,
        scale=120,
        bestEffort=True,
        maxPixels=1e9,
    ).getInfo()

    vmin_k = float(stats.get("LST_K_min") or 293.0)
    vmax_k = float(stats.get("LST_K_max") or 320.0)
    if not (vmin_k < vmax_k):
        vmin_k, vmax_k = 293.0, 320.0
    vmin_k = max(200.0, vmin_k - 1.0)
    vmax_k = min(400.0, vmax_k + 1.0)

    vis_params = {"min": vmin_k, "max": vmax_k, "palette": THERMAL_PALETTE}
    map_id = lst_image.getMapId(vis_params)
    token = map_id.get("token") or ""

    display_bbox = data_bbox_from_pixels(city_key) or config["bbox"]
    cfg_bbox = config["bbox"]

    return {
        "city_key": city_key,
        "tile_url": map_id["tile_fetcher"].url_format,
        "token": token,
        "vmin_k": round(vmin_k, 1),
        "vmax_k": round(vmax_k, 1),
        "unit": "K",
        "source": "Landsat 8 Collection 2 Level-2 ST_B10 (Google Earth Engine)",
        "palette": THERMAL_PALETTE,
        "bounds": {
            "west": display_bbox[0],
            "south": display_bbox[1],
            "east": display_bbox[2],
            "north": display_bbox[3],
        },
        "raster_bounds": {
            "west": cfg_bbox[0],
            "south": cfg_bbox[1],
            "east": cfg_bbox[2],
            "north": cfg_bbox[3],
        },
        "masked_to_city": resolve_city_boundary_geometry(city_key, config) is not None,
    }


def fetch_thermal_tile(city_key: str, z: int, x: int, y: int) -> bytes:
    """Proxy a single GEE thermal tile (avoids browser CORS / auth issues)."""
    import requests

    info = get_thermal_tiles(city_key)
    url = info["tile_url"].format(z=z, x=x, y=y)
    token = info.get("token") or ""
    if token and "token=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}token={token}"

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content
