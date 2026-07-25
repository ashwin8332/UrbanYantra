"""Spatially aware train/validation splits."""

from __future__ import annotations

import numpy as np
import pandas as pd


def spatial_holdout_split(df: pd.DataFrame, holdout_fraction: float = 0.2, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Hold out entire spatial tiles (not random pixels)."""
    tiles = df["tile_id"].unique()
    rng = np.random.default_rng(seed)
    n_hold = max(1, int(len(tiles) * holdout_fraction))
    holdout_tiles = set(rng.choice(tiles, size=n_hold, replace=False))
    test_mask = df["tile_id"].isin(holdout_tiles).values
    train_mask = ~test_mask
    return train_mask, test_mask
