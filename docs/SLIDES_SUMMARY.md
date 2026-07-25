# Slide Summary — Method & Results

## Title slide
**Optimizing Urban Heat Mitigation and Cooling Strategies via AI/ML**

## Slide 1 — Problem
- Urban heat islands increase mortality and energy demand
- Need spatially explicit hotspot maps and intervention prioritization

## Slide 2 — Data stack
- Landsat 8 LST + Sentinel-2 (10 m indices)
- WorldCover, ERA5-Land, GHSL, OSM morphology

## Slide 3 — Method
```
Ingest → Downscale LST → Feature stack → XGBoost/RF → SHAP → InVEST UCM scenarios → Rank
```

## Slide 4 — Hotspot detection
- 10 m LST surface
- Classes: normal / moderate (+2 °C) / severe (+4 °C)
- Spatial tile cross-validation

## Slide 5 — Driver attribution (SHAP)
- Top drivers: NDBI, impervious fraction, NDVI, building height
- Per-pixel dominant driver map

## Slide 6 — Scenarios
| Intervention | Mechanism | Typical ΔT |
|--------------|-----------|------------|
| Urban greening | Shade + ET | 1–2.5 °C |
| Cool roof | Albedo | 0.5–1.5 °C |
| Blue infra | Evaporation | 0.5–2 °C |

## Slide 7 — Ranked recommendations
- CSV: zone, intervention type, ΔT, complexity, confidence
- Prioritize high-impervious, low-vegetation cores for greening

## Slide 8 — Demo & repo
- One command: `py run_pipeline.py`
- Streamlit dashboard
- Open source, reproducible

## Slide 9 — Next steps
- GEE production cities, InVEST calibration, SOLWEIG microclimate
