"""Temporal feature helpers."""

from __future__ import annotations

import pandas as pd


def summarize_meteo_for_pixels(meteo_df: pd.DataFrame) -> dict[str, float]:
    """City-wide meteo summary merged to all pixels (static for snapshot LST model)."""
    return {
        "temp_2m_c": float(meteo_df["temp_2m_c"].mean()),
        "dewpoint_c": float(meteo_df["dewpoint_c"].mean()),
        "humidity_proxy": float(meteo_df["humidity_proxy"].mean()),
        "wind_ms": float(meteo_df["wind_ms"].mean()),
        "solar_radiation_wm2": float(meteo_df["solar_radiation_wm2"].mean()),
        "hour": int(meteo_df.loc[meteo_df["solar_radiation_wm2"].idxmax(), "hour"]),
        "month": int(meteo_df["month"].mode().iloc[0]),
        "season": int(meteo_df["season"].mode().iloc[0]),
        "heatwave_flag": int(meteo_df["heatwave_flag"].max()),
    }
