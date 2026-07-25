"""10 m LST downscaling using Sentinel-2 indices (NDVI/NDBI residual adjustment)."""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LinearRegression


def downscale_lst(lst_coarse: np.ndarray, ndvi: np.ndarray, ndbi: np.ndarray) -> np.ndarray:
    """
    Downscale coarse LST to fine resolution using vegetation/built-up structure.

    Method (PDF stack): fit LST ~ NDVI + NDBI on coarse grid, apply coefficients at 10 m.
    """
    h, w = ndvi.shape
    if lst_coarse.shape != (h, w):
        from scipy.ndimage import zoom

        zy = h / lst_coarse.shape[0]
        zx = w / lst_coarse.shape[1]
        lst_up = zoom(lst_coarse, (zy, zx), order=1)
    else:
        lst_up = lst_coarse.copy()

    X = np.column_stack([ndvi.ravel(), ndbi.ravel()])
    y = lst_up.ravel()
    valid = np.isfinite(X).all(axis=1) & np.isfinite(y)
    reg = LinearRegression()
    reg.fit(X[valid], y[valid])
    lst_pred = reg.predict(X).reshape(h, w)
    # Blend upsampled LST with index-based prediction (weights from literature-style hackathon default)
    alpha = 0.35
    lst_10m = (1 - alpha) * lst_up + alpha * lst_pred
    return lst_10m.astype(np.float32)
