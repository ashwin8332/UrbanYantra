"""Fast surrogate ΔT model for real-time scenario sliders (Phase 5)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from simulation.invest_ucm import invest_ucm_delta_t

logger = logging.getLogger(__name__)

# Intervention parameter ranges for sampling
PARAM_RANGES = {
    "canopy_pct": (0.0, 0.50),
    "albedo_delta": (0.0, 0.35),
    "water_pct": (0.0, 0.15),
}


def _sample_scenarios(n_samples: int, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(n_samples):
        samples.append(
            [
                rng.uniform(*PARAM_RANGES["canopy_pct"]),
                rng.uniform(*PARAM_RANGES["albedo_delta"]),
                rng.uniform(*PARAM_RANGES["water_pct"]),
            ]
        )
    return np.array(samples, dtype=np.float32)


def _combined_delta_t(
    lst: np.ndarray,
    ndvi: np.ndarray,
    impervious: np.ndarray,
    canopy_pct: float,
    albedo_delta: float,
    water_pct: float,
) -> float:
    """Sum cooling from three intervention channels at grid mean conditions."""
    green = invest_ucm_delta_t(
        lst,
        ndvi,
        impervious,
        "urban_greening",
        {"canopy_increase_pct": canopy_pct * 100, "shade_factor": 0.15},
    )
    roof = invest_ucm_delta_t(
        lst,
        ndvi,
        impervious,
        "cool_roof",
        {"albedo_increase": albedo_delta, "roof_fraction": 0.35},
    )
    water = invest_ucm_delta_t(
        lst,
        ndvi,
        impervious,
        "blue_infrastructure",
        {"water_fraction_increase": water_pct, "evap_cooling_c": 1.5},
    )
    return float(np.mean(green + roof + water))


def fit_surrogate_model(
    config: dict,
    out_dir: Path,
    n_samples: int = 40,
) -> dict:
    """
    Fit linear surrogate: (canopy_pct, albedo_delta, water_pct) → mean ΔT (°C).

    Enables dashboard sliders without re-running InVEST on every drag.
    """
    sim_dir = out_dir / "simulation"
    sim_dir.mkdir(parents=True, exist_ok=True)
    raster_dir = out_dir / "rasters"

    import rasterio

    with rasterio.open(raster_dir / "lst_10m.tif") as src:
        lst = src.read(1).astype(np.float32)
    with rasterio.open(raster_dir / "ndvi.tif") as src:
        ndvi = src.read(1).astype(np.float32)
    imp_path = raster_dir / "impervious_frac.tif"
    if imp_path.exists():
        with rasterio.open(imp_path) as src:
            impervious = src.read(1).astype(np.float32)
    else:
        impervious = 1 - ndvi

    X = _sample_scenarios(n_samples)
    y = np.array(
        [_combined_delta_t(lst, ndvi, impervious, *row) for row in X],
        dtype=np.float32,
    )

    model = LinearRegression()
    model.fit(X, y)
    joblib.dump(model, sim_dir / "surrogate_delta_t.joblib")

    feature_names = ["canopy_pct", "albedo_delta", "water_pct"]
    meta = {
        "feature_names": feature_names,
        "intercept": float(model.intercept_),
        "coefficients": {n: float(c) for n, c in zip(feature_names, model.coef_)},
        "r2_train": float(model.score(X, y)),
        "n_samples": n_samples,
        "note": "TODO: source actual intervention costs from municipal data",
    }
    meta_path = sim_dir / "surrogate_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("Surrogate fitted (train R²=%.3f): %s", meta["r2_train"], meta_path)
    return {"model": model, "meta": meta, "path": sim_dir / "surrogate_delta_t.joblib"}


def predict_surrogate(
    canopy_pct: float,
    albedo_delta: float,
    water_pct: float,
    model_path: Path,
) -> float:
    model = joblib.load(model_path)
    return float(model.predict([[canopy_pct, albedo_delta, water_pct]])[0])
