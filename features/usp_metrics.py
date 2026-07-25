"""
Hackathon USP metrics — Tree/Green cooling, Carbon mitigation, Urban Planning priority.

Tied to PS1 outcomes: optimized intervention type, spatial placement, estimated ΔT.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# IPCC-style rough sequestration: ~0.06 t CO₂/tree/year; 400 trees/km² at 25% greening
CO2_TONS_PER_CANOPY_PCT_KM2 = 2.4


def green_cooling_effect(ndvi: np.ndarray, canopy_increase_pct: float, shade_factor: float = 0.15) -> np.ndarray:
    """
    Tree / urban greening cooling via evapotranspiration + shade (greenhouse mitigation on local heat).
    Returns ΔT (negative = cooling) per pixel.
    """
    ndvi_deficit = np.clip(0.45 - ndvi, 0, 0.45)
    intensity = canopy_increase_pct / 100.0
    evap = ndvi_deficit * intensity * 2.2
    shade = intensity * shade_factor * 3.5
    return -(evap + shade)


def carbon_sequestration_tons(
    urban_greening_pct: float,
    area_km2: float,
    green_roofs_pct: float = 0.0,
) -> float:
    """Estimated annual CO₂ uptake from tree cover + green roofs (t CO₂/yr)."""
    tree_co2 = (urban_greening_pct / 100.0) * area_km2 * CO2_TONS_PER_CANOPY_PCT_KM2
    roof_co2 = (green_roofs_pct / 100.0) * area_km2 * 0.8
    return round(tree_co2 + roof_co2, 1)


def urban_planning_priority_score(df: pd.DataFrame) -> pd.Series:
    """
    Rank pixels for intervention placement: high LST + low NDVI + high impervious + near population.
    Score 0–100 (higher = plan green infrastructure here first).
    """
    lst_norm = (df["lst_c"] - df["lst_c"].min()) / (df["lst_c"].max() - df["lst_c"].min() + 1e-6)
    ndvi_penalty = 1.0 - np.clip(df["ndvi"] / 0.5, 0, 1)
    imp = np.clip(df.get("impervious_frac", df.get("ndbi", 0.5)), 0, 1)
    pop = df.get("population", pd.Series(1.0, index=df.index))
    pop_norm = (pop - pop.min()) / (pop.max() - pop.min() + 1e-6)
    score = (0.35 * lst_norm + 0.30 * ndvi_penalty + 0.20 * imp + 0.15 * pop_norm) * 100
    return score.clip(0, 100)


def attach_usp_columns(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Add USP columns to feature table for API / rankings."""
    out = df.copy()
    out["planning_priority"] = urban_planning_priority_score(out)
    bbox = config["bbox"]
    area_km2 = _bbox_area_km2(bbox)
    green_pct = config.get("scenarios", {}).get("urban_greening", {}).get("canopy_increase_pct", 25)
    out["co2_mitigation_tons_yr"] = carbon_sequestration_tons(green_pct, area_km2)
    shade = config.get("scenarios", {}).get("urban_greening", {}).get("shade_factor", 0.15)
    if "ndvi" in out.columns:
        out["green_cooling_potential_c"] = -green_cooling_effect(
            out["ndvi"].values, green_pct, shade
        )
    return out


def _bbox_area_km2(bbox: list[float]) -> float:
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_mid = (min_lat + max_lat) / 2
    m_per_deg_lat = 111.32
    m_per_deg_lon = 111.32 * np.cos(np.radians(lat_mid))
    return (max_lon - min_lon) * m_per_deg_lon * (max_lat - min_lat) * m_per_deg_lat
