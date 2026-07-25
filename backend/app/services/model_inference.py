"""Live AIML inference — load trained XGBoost models and predict LST / hotspots."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import joblib
import numpy as np
import pandas as pd

from backend.app.services.city_data import _load_feature_table, _city_out_dir
from features.feature_columns import FEATURE_COLUMNS

HOTSPOT_LABELS = {0: "normal", 1: "moderate", 2: "severe"}


@lru_cache(maxsize=8)
def _load_models(city_key: str) -> tuple[Any, Any]:
    out = _city_out_dir(city_key)
    reg_path = out / "models" / "xgb_lst_regressor.joblib"
    clf_path = out / "models" / "xgb_hotspot_classifier.joblib"
    if not reg_path.exists() or not clf_path.exists():
        raise FileNotFoundError(
            f"No trained models for {city_key}. Run: py run_pipeline.py --city {city_key}"
        )
    return joblib.load(reg_path), joblib.load(clf_path)


def get_model_metrics(city_key: str) -> dict[str, Any]:
    """Spatial holdout metrics from pipeline training."""
    metrics_path = _city_out_dir(city_key) / "models" / "metrics.json"
    if not metrics_path.exists():
        raise FileNotFoundError(f"No model metrics for {city_key}. Run the pipeline first.")
    raw = json.loads(metrics_path.read_text(encoding="utf-8"))
    return {
        "city_key": city_key,
        "model": "XGBoost",
        "validation": "spatial_tile_holdout",
        "lst_regression": {
            "mae_c": round(float(raw["xgb_lst_mae"]), 3),
            "r2": round(float(raw["xgb_lst_r2"]), 3),
            "rf_mae_c": round(float(raw.get("rf_lst_mae", 0)), 3),
            "rf_r2": round(float(raw.get("rf_lst_r2", 0)), 3),
        },
        "hotspot_classifier": {
            "accuracy": round(float(raw["xgb_hotspot_acc"]), 3),
        },
        "feature_count": len(FEATURE_COLUMNS),
    }


def _nearest_row(df: pd.DataFrame, lon: float, lat: float) -> pd.Series:
    dist = (df["lon"] - lon) ** 2 + (df["lat"] - lat) ** 2
    return df.loc[dist.idxmin()]


def _row_features(row: pd.Series) -> np.ndarray:
    missing = [c for c in FEATURE_COLUMNS if c not in row.index]
    if missing:
        raise ValueError(f"Feature table missing columns: {missing}")
    return row[FEATURE_COLUMNS].values.astype(np.float32).reshape(1, -1)


def predict_lst(city_key: str, lon: float, lat: float) -> dict[str, Any]:
    """Predict LST at nearest pixel to the given coordinate."""
    df = _load_feature_table(city_key)
    row = _nearest_row(df, lon, lat)
    reg, _ = _load_models(city_key)
    X = _row_features(row)
    predicted = float(reg.predict(X)[0])
    observed = float(row["lst_c"])
    calibrated = float(row.get("lst_calibrated_c", observed))
    return {
        "city_key": city_key,
        "lon": float(lon),
        "lat": float(lat),
        "pixel_lon": float(row["lon"]),
        "pixel_lat": float(row["lat"]),
        "observed_lst_c": round(observed, 2),
        "observed_lst_calibrated_c": round(calibrated, 2),
        "predicted_lst_c": round(predicted, 2),
        "residual_c": round(observed - predicted, 2),
        "model": "xgb_lst_regressor",
    }


def predict_hotspot(city_key: str, lon: float, lat: float) -> dict[str, Any]:
    """Predict hotspot class and probabilities at nearest pixel."""
    df = _load_feature_table(city_key)
    row = _nearest_row(df, lon, lat)
    _, clf = _load_models(city_key)
    X = _row_features(row)
    pred_class = int(clf.predict(X)[0])
    proba = clf.predict_proba(X)[0]
    classes = [int(c) for c in clf.classes_]
    return {
        "city_key": city_key,
        "lon": float(lon),
        "lat": float(lat),
        "pixel_lon": float(row["lon"]),
        "pixel_lat": float(row["lat"]),
        "observed_hotspot_class": int(row.get("hotspot_class", pred_class)),
        "predicted_hotspot_class": pred_class,
        "hotspot_label": HOTSPOT_LABELS.get(pred_class, str(pred_class)),
        "probabilities": [
            {
                "class": cls,
                "label": HOTSPOT_LABELS.get(cls, str(cls)),
                "probability": round(float(proba[i]), 3),
            }
            for i, cls in enumerate(classes)
        ],
        "model": "xgb_hotspot_classifier",
    }


def predict_point(city_key: str, lon: float, lat: float) -> dict[str, Any]:
    """Combined LST + hotspot prediction for map click."""
    lst = predict_lst(city_key, lon, lat)
    hotspot = predict_hotspot(city_key, lon, lat)
    return {
        "city_key": city_key,
        "lon": lst["lon"],
        "lat": lst["lat"],
        "pixel_lon": lst["pixel_lon"],
        "pixel_lat": lst["pixel_lat"],
        "observed_lst_c": lst["observed_lst_c"],
        "observed_lst_calibrated_c": lst.get("observed_lst_calibrated_c", lst["observed_lst_c"]),
        "predicted_lst_c": lst["predicted_lst_c"],
        "residual_c": lst["residual_c"],
        "observed_hotspot_class": hotspot["observed_hotspot_class"],
        "predicted_hotspot_class": hotspot["predicted_hotspot_class"],
        "hotspot_label": hotspot["hotspot_label"],
        "probabilities": hotspot["probabilities"],
        "lst_model": lst["model"],
        "hotspot_model": hotspot["model"],
    }


def build_predictions_grid_geojson(city_key: str, stride: int = 4) -> dict[str, Any]:
    """GeoJSON grid of observed vs AI-predicted LST for map overlay."""
    df = _load_feature_table(city_key)
    sub = df[(df["row"] % stride == 0) & (df["col"] % stride == 0)].copy()
    if sub.empty:
        sub = df.iloc[:: max(1, stride * stride)].copy()

    reg, clf = _load_models(city_key)
    X = sub[FEATURE_COLUMNS].values.astype(np.float32)
    lst_pred = reg.predict(X)
    hotspot_pred = clf.predict(X)

    observed = sub["lst_c"].values
    mae = float(np.mean(np.abs(observed - lst_pred)))
    ss_res = float(np.sum((observed - lst_pred) ** 2))
    ss_tot = float(np.sum((observed - observed.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    features = []
    for i, (_, row) in enumerate(sub.iterrows()):
        pred = float(lst_pred[i])
        obs = float(row["lst_c"])
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
                "properties": {
                    "observed_lst_c": round(obs, 2),
                    "predicted_lst_c": round(pred, 2),
                    "residual_c": round(obs - pred, 2),
                    "hotspot_class": int(hotspot_pred[i]),
                    "hotspot_label": HOTSPOT_LABELS.get(int(hotspot_pred[i]), "unknown"),
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "city_key": city_key,
            "stride": stride,
            "point_count": len(features),
            "grid_mae_c": round(mae, 3),
            "grid_r2": round(r2, 3),
            "model": "xgb_lst_regressor",
        },
    }
