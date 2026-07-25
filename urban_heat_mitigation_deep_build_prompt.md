# Urban Heat Mitigation — Deep Build Prompt
**Geospatial AI/ML + Physics-Informed Cooling Optimization | India Multi-City Pilot**

Scope locked in: India, week+ research-grade build, pipeline + lightweight dashboard.

---

## 0. How to use this file

- **Section 1** is a self-contained master prompt. Paste it into Claude Code (or any coding agent) to scaffold the whole repo in one go.
- **Sections 2–12** are the reference spec the master prompt points back to — pull individual phases out as smaller prompts if you'd rather build incrementally and review between steps (recommended for a hackathon — you want working checkpoints, not one giant unreviewed diff).
- Every resource is tagged with its ID from your resource map PDF (`R-xx` = repo, `D-xx` = dataset, `T-xx` = tool, `P-xx` = paper, `N-xx` = notebook) so you can jump straight to the source.

---

## 1. MASTER PROMPT (paste this into Claude Code)

```
You are building "UrbanYantra" — a geospatial AI/ML system for urban heat hotspot
detection, physics-informed driver attribution, and cooling-intervention optimization,
for a hackathon on Optimizing Urban Heat Mitigation via AI/ML.

SCOPE: Multi-city India pilot — Mumbai (primary, deep-dive), Delhi NCR, Bengaluru,
Ahmedabad (cross-validation cities, chosen for climate diversity: coastal humid,
semi-arid continental, tropical plateau, hot semi-arid). Ahmedabad already has a
municipal heat action plan, which gives a real-world comparison point for your results.

DELIVERABLE: (1) a Python data/ML pipeline that is fully reproducible end-to-end via
scripts, and (2) a lightweight full-stack dashboard (FastAPI backend + Next.js frontend)
that lets a judge pick a city, see the heat hotspot map, see SHAP-based driver
attribution, move sliders to simulate interventions, and see a ranked table of optimal
interventions with estimated °C reduction.

NON-NEGOTIABLE REQUIREMENT: the system must be "physics-informed," not purely
statistical. Implement this via (a) InVEST Urban Cooling Model calibrated to local
station data as the primary physics-grounded ΔT engine, and (b) a lightweight
physics-informed neural net (PINN) with a surface-energy-balance residual term as a
secondary/stretch model that judges can be shown explicitly as the "physics-informed ML"
component.

TECH STACK:
- Data/geo: Python, geemap + earthengine-api, rasterio, geopandas, osmnx, xarray, cdsapi
- ML: scikit-learn, xgboost, shap, torch (for the PINN)
- Physics sim: natcap.invest (Urban Cooling Model), invest-ucm-calibration
- Backend: FastAPI, serving precomputed GeoJSON/Parquet + on-demand scenario scoring
- Frontend: Next.js + Leaflet (OSM tiles, free) + Recharts for SHAP plots
- Storage: local Parquet/GeoTIFF/GeoJSON files — no paid DB needed for a hackathon demo

BUILD IN THIS ORDER (see full detail in the attached spec doc — replicate its phase
structure exactly, do not skip the calibration or SHAP steps even under time pressure,
they are what makes this defensible to judges):

Phase 0 — repo scaffold + config (cities.yaml with bounding boxes)
Phase 1 — data acquisition pipeline per city (Landsat 8 LST, ESA WorldCover, GHSL +
  UT-GLOBUS building heights, OSM morphology via osmnx, ERA5-Land meteorology)
Phase 2 — feature engineering (NDVI/NDBI/NDWI/UTFVI, building density, road density,
  distance-to-green/water, LCZ proxy) → one combined feature parquet per city
Phase 3 — ML modeling: XGBoost LST regression, leave-one-city-out cross-validation,
  SHAP global + per-hotspot attribution
Phase 4 — physics-informed layer: calibrate InVEST UCM per city against ERA5/station
  temps; implement the PINN stretch model with a heat-diffusion/energy-balance residual
  loss term
Phase 5 — scenario engine: generate tree-canopy / cool-roof / water-body / combined
  intervention scenarios per hotspot, score ΔT via InVEST, fit a fast surrogate model per
  hotspot so the dashboard sliders respond in real time without rerunning InVEST live,
  rank by ΔT and by ΔT-per-unit-cost
Phase 6 — FastAPI endpoints (/cities, /hotspots/{city}, /drivers/{city}, /scenario,
  /ranking/{city}) + Next.js dashboard (map, SHAP panel, scenario sliders, ranked table)
Phase 7 — validation report + README + architecture diagram for the judging round

Be explicit in code comments about which resource ID (R-xx/D-xx/T-xx/P-xx) each module
implements, so the methodology is traceable in a demo Q&A. Flag any placeholder values
(intervention costs, calibration constants) clearly as "TODO: source locally" rather
than presenting them as validated figures.

Start with Phase 0 and Phase 1. Show me the repo structure and the data acquisition
script for Mumbai before moving on.
```

---

## 2. Project Scope

| | |
|---|---|
| **Primary city** | Mumbai — coastal, humid subtropical, your home turf for ground-truthing |
| **Cross-validation cities** | Delhi NCR (semi-arid continental, extreme pollution interaction), Bengaluru (tropical plateau, rapid LULC change), Ahmedabad (hot semi-arid, has India's pioneering municipal heat action plan — built-in policy narrative) |
| **Why multi-city, not single-city** | The brief rewards driver *generalizability*, and P-05 in your resource map is explicitly an 8-city cross-validation framework the authors call "directly applicable to Indian city contexts." Doing 4 cities with leave-one-city-out validation is a stronger, more defensible claim than one city with high R² that might just be overfitting to local geography. |
| **Time budget** | Week+, structured as 7 phases (~2 weeks comfortable, compressible to ~1 week by cutting the PINN and SOLWEIG to a single hero neighborhood) |
| **Deliverable** | Reproducible Python pipeline + FastAPI/Next.js dashboard |

---

## 3. System Architecture

```
                    ┌──────────────────────────────┐
                    │   OFFLINE DATA PIPELINE       │
                    │  (run once per city, cached)  │
                    │                               │
  GEE/Landsat 8 ─────►  LST, NDVI, NDBI, NDWI       │
  ESA WorldCover ────►  Land cover (11 classes)     │
  GHSL + UT-GLOBUS ──►  Building height/density     │
  OSM (osmnx) ────────►  Roads, green space, water   │
  ERA5-Land (CDS) ────►  Air temp, RH, wind, solar    │
  CPCB (optional) ────►  Local station ground-truth   │
                    └─────────────┬────────────────┘
                                  ▼
                    ┌──────────────────────────────┐
                    │  FEATURE STORE (Parquet/Tif)  │
                    └─────────────┬────────────────┘
                                  ▼
        ┌─────────────────────────┴─────────────────────────┐
        ▼                                                     ▼
┌───────────────────┐                              ┌───────────────────────┐
│  STATISTICAL ML     │                              │  PHYSICS-INFORMED      │
│  XGBoost LST model  │                              │  InVEST UCM (calibr.) │
│  + SHAP attribution │                              │  + PINN (stretch)      │
└─────────┬───────────┘                              └───────────┬────────────┘
          │                                                       │
          └─────────────────────────┬─────────────────────────────┘
                                    ▼
                    ┌──────────────────────────────┐
                    │  SCENARIO ENGINE              │
                    │  tree/cool-roof/water sweeps   │
                    │  → ΔT per hotspot per scenario │
                    │  → surrogate model per hotspot │
                    │  → cost-effectiveness ranking  │
                    └─────────────┬────────────────┘
                                  ▼
                    ┌──────────────────────────────┐
                    │  FastAPI                      │
                    │  serves precomputed + scores   │
                    │  live scenario requests        │
                    └─────────────┬────────────────┘
                                  ▼
                    ┌──────────────────────────────┐
                    │  Next.js + Leaflet dashboard  │
                    │  map · SHAP panel · sliders ·  │
                    │  ranked intervention table     │
                    └──────────────────────────────┘
```

---

## 4. Repo Structure

```
urbanyantra/
├── config/
│   └── cities.yaml              # bbox, timezone, primary station coords per city
├── data_pipeline/
│   ├── 01_fetch_lst_lulc.py     # GEE: Landsat 8 LST, ESA WorldCover  (R-06, D-01, D-05)
│   ├── 02_fetch_morphology.py   # GHSL + UT-GLOBUS + osmnx           (D-04, D-06)
│   ├── 03_fetch_era5.py         # ERA5-Land via cdsapi                (D-03, N-09)
│   ├── 04_fetch_ground_truth.py # CPCB CAAQMS station met data (optional, offline cache)
│   └── 05_lst_downscale_10m.py  # optional Sentinel-2 downscaling     (R-12)
├── features/
│   └── build_feature_table.py   # NDVI/NDBI/NDWI/UTFVI + morphology stack
├── models/
│   ├── train_xgb_lst.py         # XGBoost + leave-one-city-out CV
│   ├── shap_attribution.py      # global + per-hotspot SHAP            (T-05, P-04)
│   └── pinn_lst.py              # stretch: physics-informed NN          (P-01)
├── physics/
│   ├── invest_ucm_runner.py     # wraps natcap.invest UCM calls          (T-02)
│   ├── calibrate_ucm.py         # simulated-annealing calibration        (R-11)
│   └── biophysical_tables/      # per-city LULC biophysical CSVs
├── scenarios/
│   ├── generate_scenarios.py    # tree/cool-roof/water/combo sweeps
│   ├── fit_surrogate.py         # fast per-hotspot ΔT(intervention) model
│   └── rank_interventions.py    # ΔT and ΔT/cost ranking
├── backend/
│   └── app/main.py              # FastAPI: /cities /hotspots /drivers /scenario /ranking
├── frontend/
│   └── (Next.js app: map, SHAP panel, scenario sliders, ranked table)
├── outputs/
│   ├── geotiffs/  geojson/  parquet/  shap_plots/  validation_report.md
└── README.md
```

---

## 5. Phase Plan

Each phase has its own copy-pasteable sub-prompt if you want to feed Claude Code one phase at a time and review between steps — recommended over the all-at-once master prompt for anything you'll have to defend live to judges.

### Phase 0 — Setup (Day 0, ~2 hrs)
**Do:** Scaffold the repo above. Write `config/cities.yaml` with bounding boxes for Mumbai, Delhi NCR, Bengaluru, Ahmedabad, plus the coordinates of 1–2 known CPCB/IMD stations per city for later calibration. Set up a GEE Cloud project (required since Google's 2024 policy change — register *today*, approval can lag) and `cdsapi` credentials for ERA5.
**Acceptance:** `python config/validate_cities.py` prints valid bboxes for all 4 cities.

### Phase 1 — Data Acquisition (Days 1–2)
**Resources:** R-06 (GEE RF mapping script, adapt for LST extraction), D-01 (Landsat 8 LST), D-05 (ESA WorldCover), D-04 (GHSL), D-06 (OSM via osmnx), D-03 (ERA5-Land), D-10 (HLS L30, optional).
**Do:**
- Pull Landsat 8 Collection 2 L2 ST_B10 for each city, summer months (Mar–Jun for India, pre-monsoon peak heat), convert to °C: `LST = ST_B10 * 0.00341802 + 149.0 - 273.15`.
- Pull ESA WorldCover 10m land cover.
- Pull GHSL building height/built-up surface; also pull **UT-GLOBUS** (building heights + urban canopy parameters for 1200+ cities, available via the GEE community catalog `gee-community-catalog.org/projects/utglobus` or Zenodo) — it's purpose-built for SOLWEIG/heat-comfort work and has tighter validation than GHSL alone for this use case.
- Use `osmnx` to pull building footprints, roads, parks, water bodies per city.
- Use `cdsapi` to pull ERA5-Land 2m temperature, dewpoint, wind, solar radiation for the same date range.
- **Optional ground-truth layer:** CPCB CAAQMS stations also log temperature/humidity/wind alongside pollutants. There's no clean public REST API — data comes from the CCR portal (`app.cpcbccr.com/ccr`) via an "advanced search" UI with date-range limits per request (shorter windows for finer time resolution). Budget time to batch-download and cache this manually rather than depending on any unofficial wrapper for your live demo; use it only for offline calibration in Phase 4.
**Acceptance:** one GeoTIFF/GeoJSON bundle per city in `outputs/geotiffs/{city}/`, visually sane (open in QGIS or `rasterio` plot — LST should look like a plausible heat map, not noise).

### Phase 2 — Feature Engineering (Days 2–3)
**Resources:** R-03 (260-feature reference for structure), R-04 (UTFVI feature), T-04 (osmnx/geopandas morphology).
**Do:** Build one combined feature table per city with: `lst_celsius` (target), `ndvi`, `ndbi`, `ndwi`, `utfvi = (lst - lst_mean)/lst_mean`, `building_height_mean`, `plan_area_fraction` (UT-GLOBUS λp), `building_density`, `road_density`, `dist_to_green_m`, `dist_to_water_m`, `elevation_m`, `slope_deg`, `air_temp_2m`, `rh_2m`, `wind_speed_10m`, `solar_radiation_down`, `lcz_class` (derive a simple proxy from building height + impervious fraction if you don't have time for full LCZ classification), `population_density`, `city` (categorical, for pooling).
**Acceptance:** `features/{city}.parquet` exists for all 4 cities with no NaN target rows; a quick correlation heatmap shows NDVI negatively and NDBI/building density positively correlated with LST (sanity check that your physical intuition holds before you trust the model).

### Phase 3 — ML Modeling + Explainability (Days 3–5)
**Resources:** T-05 (SHAP), P-04 (XGBoost-SHAP driver paper), P-05 (cross-city XAI methodology — your explicit template for the India adaptation), R-01 (Getis-Ord Gi* hotspot detection).
**Do:**
- Train XGBoost regression on pooled 4-city data. Run **leave-one-city-out cross-validation**: train on 3 cities, test on the 4th, report per-city R²/RMSE. This is your generalizability claim.
- Run Getis-Ord Gi* (or simple top-decile LST clustering) to extract hotspot polygons per city.
- Run SHAP: global summary plot, dependence plots for top 5 drivers, and a per-hotspot waterfall plot (clicking a hotspot in the dashboard should show "why is this pixel hot" via SHAP, not just "it's hot").
**Acceptance:** `outputs/shap_plots/` populated; a validation table comparing in-city vs. leave-one-city-out R² (expect leave-one-out to be lower — report it honestly, that honesty is itself a credibility signal to judges).

### Phase 4 — Physics-Informed Layer (Days 5–7)
**Resources:** T-02 (InVEST UCM), R-11 (calibration via simulated annealing), P-03 (validated InVEST calibration + Paris scenario, your code template), P-01 (PINN methodology, stretch).
**Do:**
- Set up InVEST UCM per city: LULC raster, reference evapotranspiration raster, biophysical table (shade/Kc/albedo per LULC class — start from InVEST's sample tables, adjust for Indian materials where you have data).
- Calibrate `uhi_max` and related parameters per city against your ERA5/CPCB station ground truth using `invest-ucm-calibration`'s simulated annealing.
- **Stretch — PINN:** train a small MLP `f(features) → LST` with a combined loss:
  ```python
  # Illustrative skeleton — not production code, adapt to your raster grid
  import torch, torch.nn as nn

  class HeatPINN(nn.Module):
      def __init__(self, n_features):
          super().__init__()
          self.net = nn.Sequential(
              nn.Linear(n_features, 64), nn.Tanh(),
              nn.Linear(64, 64), nn.Tanh(),
              nn.Linear(64, 1)
          )
      def forward(self, x):
          return self.net(x)

  def physics_residual(pred_lst, ndvi, albedo, wind, solar_rad):
      # Simplified surface energy balance residual:
      # net_radiation - sensible_heat - latent_heat(via NDVI as ET proxy) ≈ 0 at equilibrium
      net_radiation = solar_rad * (1 - albedo)
      sensible_heat = 0.4 * pred_lst * (1 + 0.1 * wind)       # crude bulk transfer proxy
      latent_heat   = 0.3 * ndvi * pred_lst                    # ET cooling scales with greenness
      return net_radiation - sensible_heat - latent_heat

  def loss_fn(pred, target, ndvi, albedo, wind, solar_rad, lam=0.1):
      mse = nn.functional.mse_loss(pred, target)
      residual = physics_residual(pred, ndvi, albedo, wind, solar_rad)
      physics_loss = (residual ** 2).mean()
      return mse + lam * physics_loss
  ```
  Treat the energy-balance coefficients above as starting points to tune, not physical constants — the point for judging purposes is that the loss function is genuinely constrained by a physical equation, not that the exact bulk-transfer coefficients are textbook-precise.
**Acceptance:** InVEST runs cleanly per city with a calibration RMSE you can report; if you build the PINN, show that adding the physics loss term improves or matches pure-MSE performance while producing more physically plausible spatial gradients (smoother, no implausible hot/cold pixel noise).

### Phase 5 — Scenario Simulation & Optimization (Days 7–9)
**Resources:** T-01/T-02 (InVEST + SOLWEIG), R-10 (Lausanne greening scenario template), P-01 (plausibility bounds), N-08 (TreePlanter, optional for one hero neighborhood).
**Do:**
- For each hotspot polygon, define scenarios: tree canopy +20%/+40%, cool-roof albedo +0.15/+0.30, water feature +5% area, and a combined scenario.
- Run each scenario through your calibrated InVEST UCM (swap the relevant biophysical table rows) → ΔT per scenario.
- Sample ~30–50 parameter combinations per hotspot and fit a fast surrogate (linear regression or small gradient-boosted model) mapping `(tree_pct, albedo_delta, water_pct) → ΔT`. This is what lets your dashboard sliders feel instant instead of re-running InVEST on every drag.
- Rank interventions by ΔT and by ΔT per unit estimated cost. **Mark cost figures explicitly as placeholders** (e.g., `# TODO: source actual ₹/sqm tree-planting and cool-roof-coating costs from municipal data`) rather than presenting invented numbers as researched figures.
- Optional hero feature: run SOLWEIG/UMEP TreePlanter (N-07, N-08) for one Mumbai neighborhood at 1m resolution, export a static Tmrt before/after map image for the dashboard — full SOLWEIG needs QGIS desktop and won't run live in your FastAPI backend, so treat it as a precomputed asset, not a live endpoint.
**Acceptance:** `outputs/ranking/{city}.json` — ranked table of `{hotspot_id, intervention_type, estimated_delta_T, cost_effectiveness_score}`.

### Phase 6 — API + Dashboard (Days 9–12)
**Do:**
- FastAPI endpoints: `GET /cities`, `GET /hotspots/{city}` (GeoJSON), `GET /drivers/{city}` (SHAP summary JSON), `POST /scenario` (body: city, hotspot_id, intervention params → returns ΔT via the surrogate model), `GET /ranking/{city}`.
- Next.js + Leaflet dashboard: city selector, LST/hotspot map layer, click-a-hotspot SHAP waterfall panel, scenario sliders wired to `/scenario`, ranked intervention table, and a short "methodology" panel summarizing data sources and validation numbers for judges.
**Acceptance:** you can demo end-to-end on localhost — pick a city, see hotspots, click one, see why it's hot, drag a slider, see ΔT update, see the ranked table.

### Phase 7 — Validation & Packaging (Days 12–14)
**Do:** Write `validation_report.md` consolidating: per-city and leave-one-city-out R²/RMSE, InVEST calibration RMSE vs. station data, SHAP top-driver consistency across cities, and a plausibility check of your scenario ΔT estimates against P-01's reported ranges (1.3–1.8°C average, 6–8°C max local cooling from green infrastructure in Bologna/DC) — explicitly as a sanity bound, not a guarantee that Indian cities will match.
**Acceptance:** README with setup instructions, architecture diagram, and the validation report — this is what gets read first when judges aren't watching your live demo.

---

## 6. Feature Schema (reference)

| Column | Source | Notes |
|---|---|---|
| `lst_celsius` | Landsat 8 ST_B10 (D-01) | Target variable |
| `ndvi`, `ndbi`, `ndwi` | Landsat/Sentinel-2 bands | Standard normalized-difference indices |
| `utfvi` | Derived | `(lst - lst_mean)/lst_mean` |
| `building_height_mean`, `plan_area_fraction` | GHSL (D-04) + UT-GLOBUS | UT-GLOBUS gives finer canopy parameters, ~9m RMSE vs LiDAR |
| `building_density`, `road_density`, `dist_to_green_m`, `dist_to_water_m` | OSM via osmnx (D-06, T-04) | |
| `elevation_m`, `slope_deg` | SRTM DEM | |
| `air_temp_2m`, `rh_2m`, `wind_speed_10m`, `solar_radiation_down` | ERA5-Land (D-03) | |
| `lcz_class` | Derived proxy or full LCZ classification | Stratify SHAP analysis by this |
| `population_density` | GHS-POP | For exposure/vulnerability framing |
| `city` | Categorical | Needed for leave-one-city-out CV |

---

## 7. Model Validation Plan, Mapped to the Hackathon's "Outcomes"

| Hackathon outcome | Your deliverable |
|---|---|
| Heat Stress Maps identifying hotspots | `outputs/geojson/hotspots_{city}.geojson` + dashboard map layer |
| Quantitative driver assessment | SHAP global summary + per-LCZ dependence plots + cross-city consistency table |
| Validated AIML model capturing heat dynamics | Leave-one-city-out R²/RMSE table + InVEST calibration RMSE against station data |
| Scenario-based cooling evaluation | `outputs/ranking/{city}.json` — intervention type × location × estimated °C reduction, ranked |

---

## 8. Known Risks & Access Caveats

- **GEE registration**: Google now requires a registered Cloud project for Earth Engine — do this on Day 0, approval can take time.
- **Descartes Labs API** (used by the legacy WRI repo R-07/A-01 for albedo) is restricted/hard to access now — substitute Sentinel-2-derived albedo proxies via Planetary Computer instead of chasing Descartes Labs registration.
- **EY 2025 challenge dataset (D-09)** license is non-commercial/research-only — fine for a hackathon demo, but don't repackage it as an open dataset in anything beyond the competition.
- **CPCB data** has no clean public API; expect manual, rate-limited portal downloads. Cache aggressively, use only for offline calibration, not live serving.
- **UT-GLOBUS** building heights have ~9m RMSE vs LiDAR — fine for city-scale UCM/SOLWEIG work, not for claims about individual buildings.
- **SOLWEIG/UMEP** requires QGIS desktop — don't try to containerize it for live API serving; precompute static outputs for your hero neighborhood instead.

---

## 9. Resource Index (condensed)

| ID | What | Used in Phase |
|---|---|---|
| R-01 | UHI-Analysis (Getis-Ord Gi*, SHAP) | 3 |
| R-03 | EYDS2025 (260-feature reference) | 2 |
| R-06 | GEE RF UHI mapping (zero-install LST script) | 1 |
| R-10 | Lausanne InVEST greening scenario | 5 |
| R-11 | InVEST UCM calibration (simulated annealing) | 4 |
| R-12 | LST 10m downscaling | 1 (optional) |
| R-13 | IBM Granite LST foundation model | 1 (optional, gap-filling) |
| D-01 | Landsat 8 LST | 1 |
| D-03 | ERA5-Land | 1 |
| D-04 | GHSL | 1 |
| D-06 | OSM | 1 |
| D-09 | EY 2025 labeled dataset | 3 (validation reference) |
| T-01 | UMEP/SOLWEIG + TreePlanter | 5 (hero neighborhood) |
| T-02 | InVEST UCM | 4, 5 |
| T-04 | osmnx/geopandas | 2 |
| T-05 | SHAP | 3 |
| P-01 | PINN heat diffusion methodology | 4 |
| P-03 | InVEST calibration + Paris validation | 4 |
| P-04 | XGBoost-SHAP driver paper | 3 |
| P-05 | Cross-city XAI framework (India-applicable) | 3 |
| N-08 | TreePlanter tutorial | 5 |
| UT-GLOBUS | Building heights/canopy params, 1200+ cities | 1 |
| CPCB CAAQMS | Indian station met ground truth | 1, 4 (offline) |
