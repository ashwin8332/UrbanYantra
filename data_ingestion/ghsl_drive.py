"""GHSL from Hugging Face cache — sync India tile zips and pick the tile overlapping each city bbox."""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import rasterio
from rasterio.warp import transform, transform_bounds

from data_ingestion.remote_cache import _cache_root, ensure_urban_dataset_cached

logger = logging.getLogger(__name__)

LAYER_TOKENS = {
    "ghsl_built_s": ("BUILT_S", "Built - S", "Built-S", "built_s"),
    "ghsl_smod": ("SMOD", "SMOD"),
    "ghsl_built_h": ("BUILT_H", "Built - H", "Built-H", "built_h"),
}


def _matches_layer(path: Path, tokens: tuple[str, ...]) -> bool:
    name = path.name.upper()
    return any(t.upper().replace(" ", "_").replace("-", "_") in name.replace("-", "_") for t in tokens)


def _find_layer_archives(root: Path, layer_key: str) -> list[Path]:
    tokens = LAYER_TOKENS.get(layer_key, (layer_key.upper(),))
    archives: list[Path] = []
    for ext in ("*.zip", "*.tif", "*.tiff"):
        for p in root.rglob(ext):
            if _matches_layer(p, tokens):
                archives.append(p)
    # Prefer deeper paths that look like Built-S / SMOD subfolders
    archives.sort(key=lambda p: (0 if any(t.lower() in str(p.parent).lower() for t in tokens) else 1, p.name))
    return archives


def _extract_tif_from_zip(zip_path: Path, cache_dir: Path) -> Path | None:
    extract_root = cache_dir / "extracted" / zip_path.stem
    if extract_root.exists():
        tifs = list(extract_root.rglob("*.tif")) + list(extract_root.rglob("*.tiff"))
        if tifs:
            return tifs[0]
    extract_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        tif_members = [m for m in zf.namelist() if m.lower().endswith((".tif", ".tiff"))]
        if not tif_members:
            zf.extractall(extract_root)
            tifs = list(extract_root.rglob("*.tif")) + list(extract_root.rglob("*.tiff"))
            return tifs[0] if tifs else None
        member = tif_members[0]
        out = extract_root / Path(member).name
        out.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, open(out, "wb") as dst:
            dst.write(src.read())
        return out


def _geotiff_path(archive: Path, cache_dir: Path) -> Path | None:
    if archive.suffix.lower() in (".tif", ".tiff"):
        return archive
    if archive.suffix.lower() == ".zip":
        return _extract_tif_from_zip(archive, cache_dir)
    return None


def _overlap_area(bounds: rasterio.coords.BoundingBox, bbox: list[float]) -> float:
    min_lon, min_lat, max_lon, max_lat = bbox
    left = max(bounds.left, min_lon)
    right = min(bounds.right, max_lon)
    bottom = max(bounds.bottom, min_lat)
    top = min(bounds.top, max_lat)
    if left >= right or bottom >= top:
        return 0.0
    return (right - left) * (top - bottom)


def _bbox_points_inside_count(src, bbox: list[float]) -> int:
    """Count city bbox center/corners that land inside the raster in its native CRS."""
    min_lon, min_lat, max_lon, max_lat = bbox
    mid_lon = (min_lon + max_lon) / 2
    mid_lat = (min_lat + max_lat) / 2
    points = [
        (mid_lon, mid_lat),
        (min_lon, min_lat),
        (min_lon, max_lat),
        (max_lon, min_lat),
        (max_lon, max_lat),
    ]
    xs, ys = transform("EPSG:4326", src.crs or "EPSG:4326", [p[0] for p in points], [p[1] for p in points])
    b = src.bounds
    return sum(1 for x, y in zip(xs, ys) if b.left <= x <= b.right and b.bottom <= y <= b.top)


def pick_ghsl_geotiff_for_bbox(config: dict, layer_key: str, bbox: list[float]) -> Path:
    """Sync Hugging Face dataset (if needed), pick India tile zip/tif that best overlaps city bbox."""
    force = bool(config.get("force_refresh"))
    root = ensure_urban_dataset_cached(config, force=force)
    cache_dir = _cache_root(config) / "ghsl_tiles"
    cache_dir.mkdir(parents=True, exist_ok=True)

    archives = _find_layer_archives(root, layer_key)
    if not archives:
        raise FileNotFoundError(
            f"No GHSL archives for {layer_key} under {root}. "
            f"Expected *BUILT_S* or *SMOD* zips in Hugging Face dataset cache."
        )

    best_path: Path | None = None
    best_score = 0.0
    for arch in archives:
        tif = _geotiff_path(arch, cache_dir)
        if tif is None or not tif.exists():
            continue
        try:
            with rasterio.open(tif) as src:
                b = src.bounds
                inside_count = _bbox_points_inside_count(src, bbox)
                if src.crs and str(src.crs) != "EPSG:4326":
                    w, s, e, n = transform_bounds(src.crs, "EPSG:4326", b.left, b.bottom, b.right, b.top)
                    from rasterio.coords import BoundingBox

                    b = BoundingBox(w, s, e, n)
                score = inside_count * 10_000.0 + _overlap_area(b, bbox)
        except Exception as exc:
            logger.warning("Skip %s: %s", arch.name, exc)
            continue
        if score > best_score:
            best_score = score
            best_path = tif

    if best_path is None or best_score <= 0:
        # Fallback: first archive (single-city dev)
        logger.warning("No bbox overlap for %s — using first archive", layer_key)
        best_path = _geotiff_path(archives[0], cache_dir)

    if best_path is None or not best_path.exists():
        raise FileNotFoundError(f"Could not open GHSL GeoTIFF for {layer_key}")

    logger.info("GHSL %s → %s (overlap %.4f deg²)", layer_key, best_path.name, best_score)
    return best_path
