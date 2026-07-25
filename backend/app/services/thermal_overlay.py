"""Georeferenced Landsat thermal PNG overlays — pixel-perfect on satellite basemap."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from utils import load_city_config

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]

PNG_NAME = "thermal_satellite.png"
META_NAME = "thermal_satellite_meta.json"
WATER_CLASS = 80
MAX_PNG_PX = 1200


def _city_out_dir(city_key: str) -> Path:
    cfg = load_city_config(ROOT / "configs" / "cities.yaml", city_key)
    return ROOT / cfg["output_dir"]


def _lst_source_path(out_dir: Path) -> Path | None:
    raw = out_dir / "raw" / "landsat_lst_raw.tif"
    if raw.exists():
        return raw
    c_path = out_dir / "rasters" / "landsat_lst_c.tif"
    if c_path.exists():
        return c_path
    return None


def _read_lst_kelvin(path: Path) -> tuple[np.ndarray, Any]:
    import rasterio

    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float32)
        if "landsat_lst_c" in path.name or path.parent.name == "rasters":
            if np.nanmedian(data) < 100:
                data = data + 273.15
        bounds = src.bounds
        transform = src.transform
        crs = src.crs
    return data, type("Src", (), {"bounds": bounds, "transform": transform, "crs": crs, "shape": data.shape})()


def _align_worldcover_mask(out_dir: Path, lst_shape, lst_transform, lst_crs) -> np.ndarray | None:
    wc_path = out_dir / "rasters" / "worldcover.tif"
    if not wc_path.exists():
        return None
    import rasterio
    from rasterio.warp import Resampling, reproject

    mask = np.zeros(lst_shape, dtype=bool)
    with rasterio.open(wc_path) as wc:
        wc_data = np.zeros(lst_shape, dtype=np.float32)
        reproject(
            source=rasterio.band(wc, 1),
            destination=wc_data,
            src_transform=wc.transform,
            src_crs=wc.crs,
            dst_transform=lst_transform,
            dst_crs=lst_crs,
            resampling=Resampling.nearest,
        )
        mask = wc_data != WATER_CLASS
    return mask


def _downsample_rgba(rgba: np.ndarray, max_px: int) -> np.ndarray:
    h, w = rgba.shape[:2]
    scale = min(1.0, max_px / max(h, w))
    if scale >= 1.0:
        return rgba
    from PIL import Image

    img = Image.fromarray((rgba * 255).astype(np.uint8), mode="RGBA")
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return np.asarray(img.resize((new_w, new_h), Image.Resampling.BILINEAR)) / 255.0


def build_thermal_overlay(city_key: str, force: bool = False) -> dict[str, Any]:
    """Render RGBA thermal PNG from Landsat Kelvin raster + WorldCover water mask."""
    out_dir = _city_out_dir(city_key)
    maps_dir = out_dir / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    png_path = maps_dir / PNG_NAME
    meta_path = maps_dir / META_NAME

    lst_path = _lst_source_path(out_dir)
    if lst_path is None:
        raise FileNotFoundError(
            f"No Landsat LST raster for {city_key}. Run: py run_pipeline.py --city {city_key}"
        )

    source_mtime = lst_path.stat().st_mtime
    wc_path = out_dir / "rasters" / "worldcover.tif"
    if wc_path.exists():
        source_mtime = max(source_mtime, wc_path.stat().st_mtime)

    if not force and png_path.exists() and meta_path.exists():
        if png_path.stat().st_mtime >= source_mtime:
            return json.loads(meta_path.read_text(encoding="utf-8"))

    lst_k, src = _read_lst_kelvin(lst_path)
    land = _align_worldcover_mask(out_dir, src.shape, src.transform, src.crs)
    if land is None:
        land = np.isfinite(lst_k)

    valid = land & np.isfinite(lst_k) & (lst_k > 280) & (lst_k < 345)
    if not valid.any():
        valid = land & np.isfinite(lst_k)

    vmin_k = float(np.percentile(lst_k[valid], 2))
    vmax_k = float(np.percentile(lst_k[valid], 98))
    if vmax_k <= vmin_k:
        vmin_k, vmax_k = 300.0, 320.0

    import matplotlib

    jet = matplotlib.colormaps["jet"]
    norm = (lst_k - vmin_k) / (vmax_k - vmin_k)
    norm = np.clip(norm, 0, 1)
    rgba = jet(norm)
    rgba[~valid, 3] = 0.0

    rgba = _downsample_rgba(rgba.astype(np.float32), MAX_PNG_PX)

    from PIL import Image

    img = Image.fromarray((rgba * 255).astype(np.uint8), mode="RGBA")
    img.save(png_path, optimize=True)

    b = src.bounds
    coordinates = [
        [float(b.left), float(b.top)],
        [float(b.right), float(b.top)],
        [float(b.right), float(b.bottom)],
        [float(b.left), float(b.bottom)],
    ]

    meta: dict[str, Any] = {
        "city_key": city_key,
        "coordinates": coordinates,
        "bounds": {
            "west": float(b.left),
            "south": float(b.bottom),
            "east": float(b.right),
            "north": float(b.top),
        },
        "vmin_k": round(vmin_k, 1),
        "vmax_k": round(vmax_k, 1),
        "unit": "K",
        "source": "Landsat 8 Collection 2 Level-2 ST_B10",
        "png": PNG_NAME,
        "width": rgba.shape[1],
        "height": rgba.shape[0],
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("Thermal overlay built: %s (%dx%d)", png_path, meta["width"], meta["height"])
    return meta


def get_thermal_overlay_meta(city_key: str) -> dict[str, Any]:
    """Return pre-built overlay metadata; rebuild only when source rasters are newer."""
    out_dir = _city_out_dir(city_key)
    meta_path = out_dir / "maps" / META_NAME
    png_path = out_dir / "maps" / PNG_NAME

    if meta_path.exists() and png_path.exists():
        lst_path = _lst_source_path(out_dir)
        # Deploy bundles ship PNG+meta without Landsat GeoTIFFs — serve cached assets.
        if lst_path is None or meta_path.stat().st_mtime >= lst_path.stat().st_mtime:
            return json.loads(meta_path.read_text(encoding="utf-8"))

    return build_thermal_overlay(city_key)


def get_thermal_overlay_png(city_key: str) -> bytes:
    get_thermal_overlay_meta(city_key)
    png_path = _city_out_dir(city_key) / "maps" / PNG_NAME
    if not png_path.exists():
        raise FileNotFoundError(f"Thermal overlay PNG missing for {city_key}")
    return png_path.read_bytes()
