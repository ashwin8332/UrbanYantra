"""Leave-one-city-out cross-validation (P-05 generalizability claim)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor

from features.build_feature_table import FEATURE_COLUMNS

logger = logging.getLogger(__name__)


def leave_one_city_out_cv(df: pd.DataFrame, out_dir: Path) -> dict:
    """
    Train on 3 cities, test on held-out 4th. Requires `city` column in feature table.
    """
    if "city" not in df.columns:
        logger.warning("LOO-CV skipped: no 'city' column in feature table")
        return {}

    cities = sorted(df["city"].unique())
    if len(cities) < 2:
        logger.warning("LOO-CV skipped: need >=2 cities, found %d", len(cities))
        return {}

    results = []
    for holdout in cities:
        train = df[df["city"] != holdout]
        test = df[df["city"] == holdout]
        X_tr, y_tr = train[FEATURE_COLUMNS].values, train["lst_c"].values
        X_te, y_te = test[FEATURE_COLUMNS].values, test["lst_c"].values

        model = XGBRegressor(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_tr, y_tr)
        pred = model.predict(X_te)
        results.append(
            {
                "holdout_city": holdout,
                "n_train": len(train),
                "n_test": len(test),
                "r2": float(r2_score(y_te, pred)),
                "mae": float(mean_absolute_error(y_te, pred)),
            }
        )
        logger.info("LOO-CV holdout=%s R²=%.3f MAE=%.2f°C", holdout, results[-1]["r2"], results[-1]["mae"])

    summary = {
        "folds": results,
        "mean_r2": float(np.mean([r["r2"] for r in results])),
        "mean_mae": float(np.mean([r["mae"] for r in results])),
    }
    model_dir = out_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / "loo_cv_metrics.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
