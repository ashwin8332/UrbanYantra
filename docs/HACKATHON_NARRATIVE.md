# Hackathon Narrative

## Problem

Indian cities face intensifying urban heat islands. Planners need **where** it is hottest, **why**, and **what interventions** deliver the most cooling per effort.

## Solution

We built an end-to-end pipeline that:

1. **Detects** hotspots from Landsat LST downscaled to 10 m with Sentinel-2
2. **Explains** drivers via XGBoost + SHAP (NDVI, impervious fraction, building height, meteo, etc.)
3. **Simulates** three interventions with InVEST UCM-inspired ΔT maps
4. **Ranks** top pixels/zones by estimated cooling benefit

## Pilot: Pune

- Bounding box over urban core
- Mar–May 2024 study window
- Runnable in **synthetic mode** for judges without GEE credentials
- Switch to `--data-mode gee` for live satellite data

## Demo flow (5 min)

1. `py run_pipeline.py` — show logs and outputs folder
2. Open `outputs/pune/maps/heat_hotspot_map.png`
3. Show SHAP global importance — "built-up and low vegetation drive heat"
4. Compare three scenario PNGs — greening vs cool roof vs blue infra
5. Open `intervention_rankings.csv` — top 10 zones with ΔT and complexity
6. `streamlit run dashboard/app.py` — interactive view

## Differentiators

- Follows ISRO resource map stack exactly (not a generic pipeline)
- Spatially honest validation (tile holdout)
- Credential-free fallback path
- Modular hooks for SOLWEIG, Granite, PINN

## Team ask

Support GEE project access and validation against municipal weather stations for production deployment.
