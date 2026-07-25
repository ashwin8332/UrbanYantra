"""Baseline Random Forest and XGBoost models with spatial CV."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor, XGBClassifier

from features.build_feature_table import FEATURE_COLUMNS
from models.spatial_cv import spatial_holdout_split

logger = logging.getLogger(__name__)


def train_baselines(config: dict, df: pd.DataFrame, out_dir: Path) -> dict:
    """Train XGBoost (primary) and Random Forest LST regression + hotspot classifier."""
    model_dir = out_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    X = df[FEATURE_COLUMNS].values
    y_lst = df["lst_c"].values
    y_hot = df["hotspot_class"].values

    holdout = config["spatial_cv"]["holdout_fraction"]
    train_mask, test_mask = spatial_holdout_split(df, holdout)

    xgb_reg = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
    )
    xgb_reg.fit(X[train_mask], y_lst[train_mask])
    pred = xgb_reg.predict(X[test_mask])
    metrics = {
        "xgb_lst_mae": float(mean_absolute_error(y_lst[test_mask], pred)),
        "xgb_lst_r2": float(r2_score(y_lst[test_mask], pred)),
    }

    rf_reg = RandomForestRegressor(n_estimators=150, max_depth=12, random_state=42, n_jobs=-1)
    rf_reg.fit(X[train_mask], y_lst[train_mask])
    pred_rf = rf_reg.predict(X[test_mask])
    metrics["rf_lst_mae"] = float(mean_absolute_error(y_lst[test_mask], pred_rf))
    metrics["rf_lst_r2"] = float(r2_score(y_lst[test_mask], pred_rf))

    xgb_clf = XGBClassifier(
        n_estimators=150,
        max_depth=5,
        learning_rate=0.1,
        random_state=42,
        n_jobs=-1,
    )
    xgb_clf.fit(X[train_mask], y_hot[train_mask])
    metrics["xgb_hotspot_acc"] = float(xgb_clf.score(X[test_mask], y_hot[test_mask]))

    joblib.dump(xgb_reg, model_dir / "xgb_lst_regressor.joblib")
    joblib.dump(rf_reg, model_dir / "rf_lst_regressor.joblib")
    joblib.dump(xgb_clf, model_dir / "xgb_hotspot_classifier.joblib")

    metrics_path = model_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    logger.info("Model metrics: %s", metrics)

    df["lst_pred"] = xgb_reg.predict(X)
    df["hotspot_pred"] = xgb_clf.predict(X)
    return {"xgb_reg": xgb_reg, "rf_reg": rf_reg, "xgb_clf": xgb_clf, "metrics": metrics, "df": df}
