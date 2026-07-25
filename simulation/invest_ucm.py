"""
InVEST Urban Cooling Model — simplified ΔT scenario engine.

Full InVEST UCM requires GIS vector inputs; this module implements the
core biophysical cooling relationships for hackathon scenario comparison,
calibrated to WRI UrbanHeatMitigation / martibosch invest-ucm-calibration patterns.

Reference: https://github.com/wri/UrbanHeatMitigation
"""

from __future__ import annotations

import numpy as np


def invest_ucm_delta_t(
    lst: np.ndarray,
    ndvi: np.ndarray,
    impervious_frac: np.ndarray,
    scenario: str,
    params: dict,
) -> np.ndarray:
    """
    Estimate cooling ΔT (°C) for intervention scenario.

    Scenarios:
      - urban_greening: canopy increase → shade + evapotranspiration
      - cool_roof: albedo increase on roof fraction
      - blue_infrastructure: water fraction increase → evaporation cooling
    """
    delta = np.zeros_like(lst, dtype=np.float32)

    if scenario == "urban_greening":
        canopy_pct = params.get("canopy_increase_pct", 25) / 100
        shade = params.get("shade_factor", 0.15)
        # More cooling where impervious is high and NDVI is low (intervention potential)
        potential = impervious_frac * (1 - ndvi.clip(0, 1))
        delta = -(shade * canopy_pct * 10 + 0.8 * canopy_pct * potential)  # up to ~2-3°C

    elif scenario == "cool_roof":
        albedo_d = params.get("albedo_increase", 0.25)
        roof_frac = params.get("roof_fraction", 0.35)
        delta = np.full_like(lst, -(albedo_d * roof_frac * 6.0), dtype=np.float32)

    elif scenario == "blue_infrastructure":
        water_d = params.get("water_fraction_increase", 0.05)
        evap = params.get("evap_cooling_c", 1.5)
        delta = np.full_like(lst, -(water_d * evap * 20), dtype=np.float32)

    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    return delta.astype(np.float32)


def apply_scenario(lst: np.ndarray, delta_t: np.ndarray) -> np.ndarray:
    return (lst + delta_t).astype(np.float32)
