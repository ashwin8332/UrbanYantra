# Technical Report — Urban Heat Mitigation Prototype

## Objective

Detect urban heat hotspots, attribute drivers with SHAP, and rank cooling interventions using the PDF-recommended geospatial ML stack.

## Data sources

| Dataset | Resolution | Role |
|---------|------------|------|
| Landsat 8 C2 L2 ST_B10 | 30 m | Baseline LST |
| Sentinel-2 SR | 10 m | NDVI, NDBI, NDWI, UTFVI; LST downscaling |
| ESA WorldCover v200 | 10 m | LULC, impervious/vegetation fractions |
| ERA5-Land | Hourly | Air temp, dew point, wind, solar |
| GHSL | ~100 m | Building height, population |
| OpenStreetMap | Vector | Building/road density |

## Methods

### LST downscaling (10 m)

Coarse Landsat LST is upsampled and adjusted via linear regression on NDVI and NDBI at 10 m (Konlavach Mengsuwan GEE UHI pattern).

### Hotspot classification

Pixels classified relative to city median LST: +2 °C moderate, +4 °C severe.

### ML models

- **XGBoost regressor** — primary LST prediction (21 features)
- **Random Forest** — baseline comparison
- **XGBoost classifier** — hotspot class
- **Spatial CV** — holdout by geographic tile, not random pixels

### Explainability

SHAP TreeExplainer: global bar/beeswarm plots; per-pixel dominant driver raster.

### Scenario simulation

Simplified InVEST Urban Cooling Model relationships (WRI / martibosch calibration repos):

1. Urban greening — canopy + shade on impervious-low-NDVI areas
2. Cool roof — albedo increase × roof fraction
3. Blue infrastructure — water fraction × evaporation cooling

## Assumptions

- Summer clear-sky composite (Mar–May for Pune pilot)
- City-wide meteo merged to all pixels (snapshot model)
- Synthetic mode uses seeded RNG for reproducible hackathon demos
- Full InVEST/SOLWEIG require additional GIS/3D setup (modular stubs included)

## Limitations

- No hourly LST time series without IBM Granite add-on
- SOLWEIG pedestrian comfort not run by default
- GEE export size limits may require tiling for large cities
- ΔT values are relative scenario indicators, not validated in situ

## Next steps

1. Enable GEE on production cities
2. Calibrate InVEST UCM against ground stations
3. Integrate VoxCity → SOLWEIG for microclimate
4. Add IBM Granite for temporal gap filling
5. PINN energy-balance branch after baseline validation
