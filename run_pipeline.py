#!/usr/bin/env python3
"""
One-command urban heat mitigation pipeline.

Usage:
  py run_pipeline.py --config configs/pilot_city.yaml
  py run_pipeline.py --city Mumbai
  py run_pipeline.py --multi-city --cities Mumbai Delhi_NCR Bengaluru Ahmedabad
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from data_ingestion import run_ingestion
from data_ingestion.cache import save_parquet
from explainability.shap_analysis import run_shap_analysis
from features.build_feature_table import build_feature_stack
from features.usp_metrics import attach_usp_columns
from models.leave_one_city_out import leave_one_city_out_cv
from models.benchmark_eval import run_benchmark_eval
from models.train_baseline import train_baselines
from outputs.export_maps import export_outputs
from pipeline.accuracy import run_accuracy_layer
from simulation.scenarios import run_scenarios
from simulation.solweig_stub import run_solweig_treeplanter
from utils import ensure_dir, load_city_config, load_config, list_city_keys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pipeline")


def run_single_city(config: dict, skip_shap: bool = False) -> pd.DataFrame:
    out_dir = ensure_dir(ROOT / config["output_dir"])
    logger.info("Running pipeline for %s (mode=%s)", config.get("city_name"), config.get("data_mode"))

    run_ingestion(config)
    df, _ = build_feature_stack(config, out_dir)
    df = attach_usp_columns(df, config)
    save_parquet(df, out_dir / "tables" / "feature_table.parquet")
    city_key = config.get("city_key", config.get("city_name", "city").replace(" ", "_"))
    df = run_accuracy_layer(config, df, out_dir, city_key)
    result = train_baselines(config, df, out_dir)
    df = result["df"]
    run_benchmark_eval(config, result["metrics"], out_dir)

    if not skip_shap:
        run_shap_analysis(config, df, result["xgb_reg"], out_dir)

    run_scenarios(config, out_dir)
    run_solweig_treeplanter(config, out_dir)
    export_outputs(config, df, out_dir)
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="Urban heat mitigation pipeline")
    parser.add_argument("--config", default="configs/pilot_city.yaml", help="Single-city YAML config")
    parser.add_argument("--city", help="City key from config/cities.yaml (overrides --config)")
    parser.add_argument("--multi-city", action="store_true", help="Run pooled multi-city pipeline")
    parser.add_argument(
        "--cities",
        nargs="+",
        default=["Mumbai", "Pune", "Delhi_NCR", "Bengaluru", "Hyderabad", "Chennai", "Kolkata"],
        help="City keys for --multi-city",
    )
    parser.add_argument("--data-mode", choices=["synthetic", "gee", "local"], help="Override data_mode")
    parser.add_argument("--force", action="store_true", help="Re-fetch GEE rasters (ignore cache)")
    parser.add_argument("--skip-shap", action="store_true", help="Skip SHAP (faster)")
    args = parser.parse_args()

    cities_yaml = ROOT / "configs" / "cities.yaml"

    if args.multi_city:
        frames = []
        for key in args.cities:
            config = load_city_config(cities_yaml, key)
            if args.data_mode:
                config["data_mode"] = args.data_mode
            if args.force:
                config["force_refresh"] = True
            df = run_single_city(config, skip_shap=args.skip_shap)
            frames.append(df)
        pooled = pd.concat(frames, ignore_index=True)
        pooled_dir = ensure_dir(ROOT / "outputs" / "multi_city")
        pooled.to_parquet(pooled_dir / "pooled_features.parquet", index=False)
        leave_one_city_out_cv(pooled, pooled_dir)
        logger.info("Multi-city pipeline complete. Pooled: %s", pooled_dir)
        return 0

    if args.city:
        config = load_city_config(cities_yaml, args.city)
    else:
        config = load_config(ROOT / args.config)

    if args.data_mode:
        config["data_mode"] = args.data_mode
    if args.force:
        config["force_refresh"] = True

    run_single_city(config, skip_shap=args.skip_shap)
    logger.info("Dashboard: streamlit run dashboard/app.py")
    if cities_yaml.exists():
        logger.info("Validate cities: py configs/validate_cities.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
