"""Urban morphology and land-cover derived features."""

from __future__ import annotations

import numpy as np
from scipy import ndimage

IMPERVIOUS_CLASSES = {50, 60}
VEGETATION_CLASSES = {10, 20, 30, 40, 90, 95, 100}
WATER_CLASS = 80


def distance_to_class(lulc: np.ndarray, target_classes: set[int], pixel_size: float = 1.0) -> np.ndarray:
    mask = np.isin(lulc.astype(int), list(target_classes))
    dist = ndimage.distance_transform_edt(~mask) * pixel_size
    return dist.astype(np.float32)


def impervious_fraction(lulc: np.ndarray, window: int = 5) -> np.ndarray:
    imp = np.isin(lulc.astype(int), list(IMPERVIOUS_CLASSES)).astype(np.float32)
    kernel = np.ones((window, window)) / (window * window)
    return ndimage.convolve(imp, kernel, mode="nearest").astype(np.float32)


def vegetation_fraction(lulc: np.ndarray, window: int = 5) -> np.ndarray:
    veg = np.isin(lulc.astype(int), list(VEGETATION_CLASSES)).astype(np.float32)
    kernel = np.ones((window, window)) / (window * window)
    return ndimage.convolve(veg, kernel, mode="nearest").astype(np.float32)


def compute_morphology_rasters(
    lulc: np.ndarray,
    building_density: np.ndarray | None = None,
    road_density: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    h, w = lulc.shape
    if building_density is None:
        building_density = impervious_fraction(lulc)
    if road_density is None:
        road_density = building_density * 0.7

    return {
        "building_density": building_density.astype(np.float32),
        "road_density": road_density.astype(np.float32),
        "dist_green_m": distance_to_class(lulc, VEGETATION_CLASSES),
        "dist_water_m": distance_to_class(lulc, {WATER_CLASS}),
        "impervious_frac": impervious_fraction(lulc),
        "vegetation_frac": vegetation_fraction(lulc),
    }
