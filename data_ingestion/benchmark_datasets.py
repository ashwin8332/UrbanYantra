"""D-07 Kaggle UHI + D-09 EY Challenge external benchmark loaders."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from data_ingestion.remote_cache import resolve_dataset

logger = logging.getLogger(__name__)


def _resolve_csv(config: dict, key: str) -> Path | None:
    return resolve_dataset(config, key)


def load_kaggle_uhi(config: dict) -> pd.DataFrame | None:
    """D-07 — Kaggle UHI monitoring tabular dataset (EDA / baseline)."""
    path = _resolve_csv(config, "kaggle_uhi_csv")
    if path is None:
        return None
    df = pd.read_csv(path)
    logger.info("Kaggle UHI (D-07): %d rows from %s", len(df), path.name)
    return df


def load_ey_uhi_training(config: dict) -> pd.DataFrame | None:
    """D-09 — EY 2025 NYC labeled UHI Index (transfer-learning validation reference)."""
    path = _resolve_csv(config, "ey_uhi_training_csv")
    if path is None:
        return None
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    if "UHI Index" in df.columns:
        df = df.rename(columns={"UHI Index": "uhi_index", "Longitude": "lon", "Latitude": "lat"})
    logger.info("EY UHI training (D-09): %d labeled points from %s", len(df), path.name)
    return df


def export_benchmark_summaries(config: dict, out_dir: Path) -> dict:
    """Write benchmark stats for dashboard / hackathon narrative."""
    out_dir = Path(out_dir)
    bench_dir = out_dir / "benchmarks"
    bench_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {}

    kaggle = load_kaggle_uhi(config)
    if kaggle is not None:
        kaggle_path = bench_dir / "kaggle_uhi_summary.json"
        summary["kaggle_uhi"] = {
            "rows": len(kaggle),
            "columns": list(kaggle.columns),
            "source": "D-07 Kaggle UHI Monitoring",
        }
        kaggle_path.write_text(json.dumps(summary["kaggle_uhi"], indent=2), encoding="utf-8")
        kaggle.to_parquet(bench_dir / "kaggle_uhi.parquet", index=False)

    ey = load_ey_uhi_training(config)
    if ey is not None:
        ey_stats = {
            "rows": len(ey),
            "uhi_index_mean": float(ey["uhi_index"].mean()) if "uhi_index" in ey.columns else None,
            "uhi_index_std": float(ey["uhi_index"].std()) if "uhi_index" in ey.columns else None,
            "lon_range": [float(ey["lon"].min()), float(ey["lon"].max())] if "lon" in ey.columns else None,
            "lat_range": [float(ey["lat"].min()), float(ey["lat"].max())] if "lat" in ey.columns else None,
            "source": "D-09 EY Open Science Challenge 2025 (NYC ground truth)",
            "note": "External validation — model trained on India cities, benchmark against NYC labels",
        }
        summary["ey_uhi"] = ey_stats
        (bench_dir / "ey_uhi_summary.json").write_text(json.dumps(ey_stats, indent=2), encoding="utf-8")
        ey.to_parquet(bench_dir / "ey_uhi_training.parquet", index=False)

    if summary:
        (bench_dir / "benchmark_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
