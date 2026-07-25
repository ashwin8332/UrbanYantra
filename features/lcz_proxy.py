"""LCZ proxy from building height + impervious fraction (spec Section 6)."""

from __future__ import annotations

import numpy as np


def derive_lcz_proxy(building_height: np.ndarray, impervious_frac: np.ndarray) -> np.ndarray:
    """
    Simplified LCZ proxy (1–10) from morphology when full LCZ classification is unavailable.

    Higher values = more compact / built-up (warmer tendency).
    """
    if building_height.shape != impervious_frac.shape:
        raise ValueError(
            f"LCZ inputs shape mismatch: building_height {building_height.shape} "
            f"vs impervious_frac {impervious_frac.shape}"
        )
    h = np.clip(building_height, 0, 50)
    imp = np.clip(impervious_frac, 0, 1)
    # Weighted score → discrete LCZ-like classes
    score = 0.6 * (h / 50.0) + 0.4 * imp
    lcz = np.clip(np.round(score * 9 + 1), 1, 10).astype(np.int8)
    return lcz
