"""SHAP explainability for driver attribution."""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap

from data_ingestion.cache import save_geotiff
from features.build_feature_table import FEATURE_COLUMNS

logger = logging.getLogger(__name__)


def run_shap_analysis(config: dict, df: pd.DataFrame, model, out_dir: Path) -> dict:
    """Global + local SHAP; export top driver raster."""
    explain_dir = out_dir / "explainability"
    explain_dir.mkdir(parents=True, exist_ok=True)

    X = df[FEATURE_COLUMNS]
    sample_n = min(2000, len(X))
    X_sample = X.sample(sample_n, random_state=42)

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)

    # Global importance bar
    plt.figure(figsize=(10, 6))
    shap.summary_plot(shap_values, X_sample, show=False, plot_type="bar")
    plt.tight_layout()
    bar_path = explain_dir / "shap_global_importance.png"
    plt.savefig(bar_path, dpi=150)
    plt.close()

    # Beeswarm
    plt.figure(figsize=(10, 6))
    shap.summary_plot(shap_values, X_sample, show=False)
    plt.tight_layout()
    beeswarm_path = explain_dir / "shap_beeswarm.png"
    plt.savefig(beeswarm_path, dpi=150)
    plt.close()

    mean_abs = np.abs(shap_values).mean(axis=0)
    importance = pd.DataFrame({"feature": FEATURE_COLUMNS, "mean_abs_shap": mean_abs}).sort_values(
        "mean_abs_shap", ascending=False
    )
    importance.to_csv(explain_dir / "shap_feature_importance.csv", index=False)

    # Driver attribution map: dominant SHAP feature per pixel (subset for speed)
    full_X = X.values
    sv_full = explainer.shap_values(full_X)
    dominant_idx = np.argmax(np.abs(sv_full), axis=1)
    driver_codes = dominant_idx.reshape(df["row"].max() + 1, df["col"].max() + 1).astype(np.float32)
    driver_path = out_dir / "rasters" / "driver_attribution.tif"
    save_geotiff(driver_codes, driver_path, config["bbox"])

    mapping = {i: FEATURE_COLUMNS[i] for i in range(len(FEATURE_COLUMNS))}
    (explain_dir / "driver_code_mapping.json").write_text(
        __import__("json").dumps(mapping, indent=2), encoding="utf-8"
    )

    logger.info("SHAP outputs saved to %s", explain_dir)
    return {
        "importance": importance,
        "bar_plot": bar_path,
        "beeswarm_plot": beeswarm_path,
        "driver_raster": driver_path,
    }
