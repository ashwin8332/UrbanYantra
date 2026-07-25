"""Spectral indices: NDVI, NDBI, NDWI, UTFVI."""

from __future__ import annotations

import numpy as np


def safe_div(num: np.ndarray, den: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return num / (den + eps)


def compute_indices_from_bands(bands: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Compute indices from Sentinel-2 band dict (B2=blue, B3=green, B4=red, B8=nir, B11=swir)."""
    green = bands.get("B3", bands.get("green"))
    red = bands.get("B4", bands.get("red"))
    nir = bands.get("B8", bands.get("nir"))
    swir = bands.get("B11", bands.get("swir"))

    ndvi = safe_div(nir - red, nir + red)
    ndbi = safe_div(swir - nir, swir + nir)
    ndwi = safe_div(green - nir, green + nir)

    # Urban Thermal Field Variance Index (UTFVI) — LST proxy from emissivity/vegetation
    # When LST unavailable at index time, approximate from NDVI (common hackathon simplification)
    lst_proxy = 35 - 8 * ndvi  # °C proxy
    urban_mean = np.nanmean(lst_proxy)
    utfvi = (lst_proxy - urban_mean) / urban_mean

    return {
        "ndvi": ndvi.astype(np.float32),
        "ndbi": ndbi.astype(np.float32),
        "ndwi": ndwi.astype(np.float32),
        "utfvi": utfvi.astype(np.float32),
    }
