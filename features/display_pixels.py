"""Shared filter for map-visible land pixels."""

from __future__ import annotations

import pandas as pd


def visible_pixels(df: pd.DataFrame) -> pd.DataFrame:
    """Pixels shown on heat grid / sample points (urban footprint + no water)."""
    if df is None or df.empty:
        return df
    if "is_excluded" in df.columns:
        return df[~df["is_excluded"]]
    if "is_water" in df.columns:
        return df[~df["is_water"]]
    return df
