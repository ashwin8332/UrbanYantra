# Real Data Integration Guide — UrbanYantra Hackathon PS1

## Synthetic vs Real — Current Audit

| Layer | Dataset ID | `data_mode=gee` | `data_mode=local` | Synthetic fallback |
|-------|-----------|-----------------|-------------------|-------------------|
| LST | D-01 Landsat 8 | ✅ GEE `LANDSAT/LC08/C02/T1_L2` | ❌ still GEE | Only if `synthetic` |
| ECOSTRESS | D-02 | ✅ GEE / HTTP COG (notebook) | — | — |
| Meteo / UTCI | D-03 ERA5 | ✅ GEE ERA5-Land or Open-Meteo | ✅ **Local NetCDF UTCI** | Removed in gee/local |
| GHSL morphology | D-04 | ✅ GEE JRC GHSL | ✅ **Local Built-S + SMOD** | Removed in gee/local |
| LULC | D-05 WorldCover | ✅ GEE | — | Only if `synthetic` |
| OSM | D-06 | ✅ osmnx | ✅ osmnx | Synthetic grid only in `synthetic` mode |
| Kaggle UHI | D-07 | — | ✅ CSV benchmark | — |
| EY Challenge | D-09 | — | ✅ NYC labels benchmark | — |
| Climate projection chart | — | ⚠️ formula | ⚠️ formula | demo curve |
| Chat / PINN | — | ⚠️ rules / stub | ⚠️ rules / stub | — |

**Default in `configs/cities.yaml`:** `data_mode: gee` (real satellite + meteo).

**To use your downloaded files:** set paths in `configs/local_datasets.yaml` and run:

```powershell
py run_pipeline.py --city Mumbai --data-mode local --force
```

---

## Your Datasets — How to Wire Them

### D-03 ERA5 UTCI NetCDF (your zip extract)

Files: `ECMWF_utci_20240301_v1.1_con.nc` … (~41 MB/day)

1. Extract zip to a folder (e.g. `Downloads/e41937b485eabac6f3a37b403badfcf1`)
2. Set `local_data.era5_utci_dir` in `configs/local_datasets.yaml`
3. Align `date_range` in `cities.yaml` with available dates (Mar 2024 in your download)

**Note:** These are **UTCI** (human heat stress), not raw 2m temperature — ideal for PS1 “heat stress maps”.

### D-04 GHSL Built-S + SMOD (Hugging Face)

Dataset repo: `sleepingbeauty11/UrbanDatasets` (folder `ghsl/` — Built-S + SMOD India tiles).

- **Built-S** → built-up surface (m²) → impervious / density features  
- **SMOD** → settlement class (urban core / suburban / rural) → LCZ proxy  
- **Built-H 2018** → optional; 2–6 year lag vs 2024 LST is **acceptable** for hackathon (cite GHSL epoch in slides)

Auto-synced on first `py run_pipeline.py --city Mumbai --data-mode local --force`, or set paths in `local_datasets.yaml`:

```yaml
ghsl_built_s: "C:/path/to/GHS_BUILT_S_...tif"
ghsl_smod: "C:/path/to/GHS_SMOD_...tif"
ghsl_built_h: ""  # optional
```

If Built-H missing, height is **proxied from Built-S**.

### D-07 Kaggle UHI — not found in Downloads yet

Set `kaggle_uhi_csv` after download. Used for EDA + baseline comparison in `outputs/{city}/benchmarks/`.

### D-09 EY Challenge — found ✅

`Training_data_uhi_index_2025-02-18.csv` (NYC, 11k+ labeled points)

Used as **external validation reference** (India-trained model vs NYC UHI labels) — not mixed into India pixel training without transfer learning.

---

## Hackathon USP (implemented in `features/usp_metrics.py`)

| USP | Metric | Where shown |
|-----|--------|-------------|
| **Tree / Green cooling** | `green_cooling_potential_c` — evapotranspiration + shade | Feature table + scenarios |
| **Carbon mitigation** | `co2_mitigation_tons_yr` — t CO₂/yr from greening | Header / scenario API |
| **Urban planning** | `planning_priority` 0–100 — where to intervene first | Rankings / future map layer |

---

## PS1 Coverage Checklist

| Objective | Status |
|-----------|--------|
| Heat hotspots + stress maps | ✅ Gi* + LST + UTCI |
| Driver quantification | ✅ SHAP + 21 features |
| AIML LST model | ✅ XGBoost + live `/predict` API |
| Physics-informed | ⚠️ InVEST UCM (simplified); PINN stub |
| Cooling scenarios | ✅ 3 interventions + surrogate |
| Optimal strategy table | ✅ rankings CSV; Phase 2 UI pending |
