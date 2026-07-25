"""Getis-Ord Gi* spatial hotspot detection (R-01)."""

from __future__ import annotations

import numpy as np
from scipy import ndimage


def getis_ord_gi_star(
    values: np.ndarray,
    kernel_size: int = 5,
    nodata: float = np.nan,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Local Getis-Ord Gi* z-scores via convolution (queen/rook-like square kernel).

    Returns (z_scores, p_values_two_tailed) same shape as input grid.
    """
    x = values.astype(np.float64)
    mask = np.isfinite(x)
    if not mask.any():
        return np.zeros_like(x, dtype=np.float32), np.ones_like(x, dtype=np.float32)

    fill = float(np.nanmean(x[mask]))
    x_filled = np.where(mask, x, fill)

    kernel = np.ones((kernel_size, kernel_size), dtype=np.float64)
    n = kernel.size
    w_sum = ndimage.convolve(np.ones_like(x_filled), kernel, mode="constant")
    local_sum = ndimage.convolve(x_filled, kernel, mode="constant")
    local_sq_sum = ndimage.convolve(x_filled**2, kernel, mode="constant")

    global_mean = x_filled[mask].mean()
    global_var = x_filled[mask].var(ddof=1)
    if global_var <= 0:
        z = np.zeros_like(x_filled, dtype=np.float32)
        p = np.ones_like(x_filled, dtype=np.float32)
        return z, p

    s = np.sqrt(global_var)
    denom = s * np.sqrt((n * w_sum - w_sum**2) / max(n - 1, 1))
    denom = np.where(denom <= 0, np.nan, denom)
    z = ((local_sum - global_mean * w_sum) / denom).astype(np.float32)

    # Two-tailed normal approximation
    from scipy.stats import norm

    p = (2 * (1 - norm.cdf(np.abs(z)))).astype(np.float32)
    z = np.where(mask, z, 0.0)
    p = np.where(mask, p, 1.0)
    return z, p


def classify_hotspots_from_gi(
    lst: np.ndarray,
    gi_z: np.ndarray,
    p_values: np.ndarray,
    moderate_delta_c: float = 2.0,
    severe_delta_c: float = 4.0,
    p_threshold: float = 0.05,
) -> np.ndarray:
    """Combine Gi* significance with LST excess above city median."""
    median_lst = float(np.nanmedian(lst))
    classes = np.zeros(lst.shape, dtype=np.int8)
    sig_hot = (p_values < p_threshold) & (gi_z > 0)
    classes[(lst >= median_lst + moderate_delta_c) & sig_hot] = 1
    classes[(lst >= median_lst + severe_delta_c) & sig_hot] = 2
    return classes
