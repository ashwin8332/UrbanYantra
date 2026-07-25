"""External benchmark evaluation — D-07 Kaggle UHI + D-09 EY NYC labels."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from data_ingestion.benchmark_datasets import load_ey_uhi_training, load_kaggle_uhi

logger = logging.getLogger(__name__)


def _kaggle_tabular_baseline(config: dict) -> dict | None:
    df = load_kaggle_uhi(config)
    if df is None or df.empty:
        return None

    target_col = "Temperature (°C)"
    feature_cols = [
        c
        for c in df.columns
        if c not in {target_col, "City Name"}
        and pd.api.types.is_numeric_dtype(df[c])
    ]
    if target_col not in df.columns or len(feature_cols) < 3:
        return None

    clean = df[feature_cols + [target_col]].dropna()
    if len(clean) < 40:
        return None

    X = clean[feature_cols].values
    y = clean[target_col].values
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)
    model = RandomForestRegressor(n_estimators=120, max_depth=10, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    return {
        "dataset": "D-07 Kaggle UHI Monitoring",
        "task": "tabular_temperature_regression",
        "rows": int(len(clean)),
        "features": feature_cols,
        "mae_c": round(float(mean_absolute_error(y_test, pred)), 3),
        "r2": round(float(r2_score(y_test, pred)), 3),
        "note": "Bundled CSV baseline — complements per-city geospatial XGBoost",
    }


def _ey_spatial_baseline(config: dict) -> dict | None:
    df = load_ey_uhi_training(config)
    if df is None or df.empty or "uhi_index" not in df.columns:
        return None

    clean = df[["lon", "lat", "uhi_index"]].dropna()
    if len(clean) < 100:
        return None

    # Subsample for speed on large NYC label set
    if len(clean) > 4000:
        clean = clean.sample(4000, random_state=42)

    X = clean[["lon", "lat"]].values
    y = clean["uhi_index"].values
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)
    model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    return {
        "dataset": "D-09 EY Open Science Challenge 2025 (NYC)",
        "task": "uhi_index_spatial_regression",
        "rows": int(len(clean)),
        "mae": round(float(mean_absolute_error(y_test, pred)), 4),
        "r2": round(float(r2_score(y_test, pred)), 3),
        "lon_range": [float(clean["lon"].min()), float(clean["lon"].max())],
        "lat_range": [float(clean["lat"].min()), float(clean["lat"].max())],
        "note": "External NYC ground-truth benchmark — India city model trained separately",
    }


def run_benchmark_eval(config: dict, city_metrics: dict, out_dir: Path) -> dict:
    """Train lightweight baselines on bundled benchmarks; merge with city XGBoost metrics."""
    out_dir = Path(out_dir)
    model_dir = out_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    payload: dict = {
        "city_metrics": city_metrics,
        "external_baselines": {},
    }

    kaggle = _kaggle_tabular_baseline(config)
    if kaggle:
        payload["external_baselines"]["kaggle_uhi"] = kaggle
        logger.info("Kaggle benchmark MAE=%.2f°C R²=%.2f", kaggle["mae_c"], kaggle["r2"])

    ey = _ey_spatial_baseline(config)
    if ey:
        payload["external_baselines"]["ey_uhi"] = ey
        logger.info("EY NYC benchmark MAE=%.4f R²=%.2f", ey["mae"], ey["r2"])

    path = model_dir / "benchmark_metrics.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Benchmark metrics → %s", path)
    return payload
