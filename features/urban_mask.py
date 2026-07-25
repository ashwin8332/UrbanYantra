"""Clip raster pixels to the urban footprint (Mumbai-style non-rectangular map extent)."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage
from shapely.geometry import box

logger = logging.getLogger(__name__)


def _build_grids(df: pd.DataFrame) -> tuple[int, int, np.ndarray, np.ndarray, np.ndarray]:
    h = int(df["row"].max()) + 1
    w = int(df["col"].max()) + 1
    water = np.zeros((h, w), dtype=bool)
    imp = np.zeros((h, w), dtype=np.float32)
    ndbi = np.zeros((h, w), dtype=np.float32)
    for row in df.itertuples(index=False):
        r, c = int(row.row), int(row.col)
        if bool(getattr(row, "is_water", False)):
            water[r, c] = True
        imp[r, c] = float(getattr(row, "impervious_frac", 0))
        ndbi[r, c] = float(getattr(row, "ndbi", 0))
    return h, w, water, imp, ndbi


def _urban_seed_mask(
    df: pd.DataFrame, water: np.ndarray, imp: np.ndarray, ndbi: np.ndarray
) -> np.ndarray:
    h, w = water.shape
    urban = np.zeros((h, w), dtype=bool)
    for row in df.itertuples(index=False):
        r, c = int(row.row), int(row.col)
        if water[r, c]:
            continue
        bld = float(getattr(row, "building_density", 0))
        pop = float(getattr(row, "population", 0))
        if imp[r, c] > 0.12 or ndbi[r, c] > -0.02 or bld > 0.0005 or pop > 30:
            urban[r, c] = True
    if not urban.any():
        urban = ~water
    return urban


def _largest_urban_blob(urban: np.ndarray) -> np.ndarray:
    structure = np.ones((9, 9), dtype=bool)
    closed = ndimage.binary_closing(urban, structure=structure)
    labeled, n = ndimage.label(closed)
    if n == 0:
        return urban
    counts = np.bincount(labeled.ravel())
    main_label = int(np.argmax(counts[1:])) + 1
    mask = labeled == main_label
    return ndimage.binary_dilation(mask, structure=np.ones((5, 5), dtype=bool))


def _peel_low_density_edges(
    mask: np.ndarray,
    imp: np.ndarray,
    ndbi: np.ndarray,
    *,
    min_imp: float = 0.14,
    min_ndbi: float = -0.02,
    border: int = 12,
    max_passes: int = 30,
) -> np.ndarray:
    """Peel low-density pixels, prioritising the outer bbox ring (removes rectangular fringe)."""
    out = mask.copy()
    h, w = out.shape
    for _ in range(max_passes):
        peel = np.zeros_like(out, dtype=bool)
        for r in range(h):
            for c in range(w):
                if not out[r, c]:
                    continue
                near_bbox = r < border or r >= h - border or c < border or c >= w - border
                on_mask_edge = False
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if nr < 0 or nr >= h or nc < 0 or nc >= w or not out[nr, nc]:
                        on_mask_edge = True
                        break
                low_density = imp[r, c] < min_imp and ndbi[r, c] < min_ndbi
                if low_density and (near_bbox or on_mask_edge):
                    peel[r, c] = True
        if not peel.any():
            break
        out[peel] = False
    return out


def apply_urban_extent_mask(
    df: pd.DataFrame,
    config: dict | None = None,
    out_dir: Path | None = None,
) -> pd.DataFrame:
    """
    Mark bbox edge / rural pixels as excluded so the map follows the city blob,
    not the full study rectangle. Coastal cities still rely on is_water for sea clip.
    """
    if df.empty or "row" not in df.columns or "col" not in df.columns:
        return df

    h, w, water, imp, ndbi = _build_grids(df)
    water_frac = float(water.sum()) / max(1, water.size)

    # All cities: clip to OSM district / city boundary when available (+ water for coastal).
    if config is not None and out_dir is not None:
        from data_ingestion.osm_city_boundary import (
            fetch_city_boundary_geometry,
            ingest_city_boundary,
            mask_pixels_to_boundary,
        )

        boundary = fetch_city_boundary_geometry(config, df=df)
        if boundary is not None:
            # Coastal fringe: OSM suburb polygons often miss narrow land strips.
            if water_frac >= 0.15:
                clip = box(config["bbox"][0], config["bbox"][1], config["bbox"][2], config["bbox"][3])
                boundary = boundary.buffer(0.002).intersection(clip)
            ingest_city_boundary(config, out_dir, df=df, geom=boundary)
            masked = mask_pixels_to_boundary(df, boundary)
            if (~masked["is_excluded"]).mean() >= 0.12:
                return masked
            logger.warning("OSM boundary left too few pixels — falling back")

    # Coastal fallback: water mask only (no urban peel — avoids clipping land peninsulas).
    if water_frac >= 0.15:
        out = df.copy()
        out["is_excluded"] = out["is_water"] if "is_water" in out.columns else False
        visible = int((~out["is_excluded"]).sum())
        logger.info(
            "Coastal water fallback: %d / %d pixels visible (%.1f%% water)",
            visible,
            len(out),
            water_frac * 100,
        )
        return out

    urban = _urban_seed_mask(df, water, imp, ndbi)
    mask = _largest_urban_blob(urban)
    mask = _peel_low_density_edges(mask, imp, ndbi)

    visible_ratio = float(mask.sum()) / max(1, float((~water).sum()))
    if visible_ratio < 0.35:
        # Large inland metros (e.g. Delhi NCR): keep urban blob, only peel bbox fringe
        mask = _largest_urban_blob(urban)
        mask = _peel_low_density_edges(
            mask, imp, ndbi, min_imp=0.10, min_ndbi=-0.05, border=8, max_passes=15
        )

    excluded = np.ones((h, w), dtype=bool)
    excluded[water] = True
    excluded[mask & ~water] = False

    out = df.copy()
    out["is_excluded"] = [bool(excluded[int(r), int(c)]) for r, c in zip(out["row"], out["col"])]
    visible = int((~out["is_excluded"]).sum())
    logger.info(
        "Urban extent mask: %d / %d pixels visible (%.1f%% excluded)",
        visible,
        len(out),
        out["is_excluded"].mean() * 100,
    )
    return out
