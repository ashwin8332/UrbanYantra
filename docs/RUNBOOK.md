# Runbook — Urban Heat Mitigation Pipeline

## Prerequisites

- Python 3.10+
- 4 GB RAM minimum
- Optional: Google Earth Engine account (`earthengine authenticate`)

## One-command run

```bash
py run_pipeline.py --config configs/pilot_city.yaml
```

## Pipeline stages

| Step | Module | Output |
|------|--------|--------|
| 1 Ingest | `data_ingestion/` | GeoTIFF rasters, Parquet tables |
| 2 Downscale LST | `preprocessing/lst_downscale.py` | `rasters/lst_10m.tif` |
| 3 Features | `features/build_feature_table.py` | `tables/feature_table.parquet` |
| 4 Train | `models/train_baseline.py` | `models/*.joblib`, metrics |
| 5 SHAP | `explainability/shap_analysis.py` | PNG + driver raster |
| 6 Scenarios | `simulation/scenarios.py` | ΔT maps, rankings CSV |
| 7 Export | `outputs/export_maps.py` | Hotspot PNG, HTML |

## GEE mode (Landsat 8 ST_B10 LST)

1. `pip install earthengine-api`
2. One-time auth (opens browser):
   ```bash
   earthengine authenticate
   ```
3. Project ID is set in `configs/cities.yaml` → `gee_project: western-avatar-491910-s2`
   (or set env `GEE_PROJECT=western-avatar-491910-s2`)
4. Re-fetch real satellite data and rebuild the dashboard cache:
   ```bash
   py run_pipeline.py --city Mumbai --data-mode gee --force
   ```
5. Restart the API (`uvicorn backend.app.main:app --reload`) so it serves the new `outputs/mumbai/` tables.

Landsat collection: `LANDSAT/LC08/C02/T1_L2`, band `ST_B10`, scaled to °C via USGS C2 factors in config.

## Fallback

`data_mode: synthetic` generates reproducible demo data (seeded RNG) when GEE/OSM unavailable.

## Dashboard

```bash
streamlit run dashboard/app.py
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| GEE auth error | Use `--data-mode synthetic` or authenticate |
| OSM timeout | Falls back to synthetic morphology automatically |
| SHAP slow | `py run_pipeline.py --skip-shap` |
| Missing scipy | `pip install scipy` |
