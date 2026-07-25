# ISRO BAH 2026 Idea Submission - UrbanYantra Answers

## Slide 1 - Cover

**Team Name:** UrbanYantra

**Problem Statement:** Optimizing Urban Heat Mitigation and Cooling Strategies via AI/ML

**Team Leader Name:** [Add team leader name]

**Solution Title:** UrbanYantra - AI/ML and satellite-driven urban heat mitigation platform

## Slide 2 - Team Members

| Name | Role | Contribution |
| --- | --- | --- |
| [Name 1] | Team Lead / Product | Problem framing, demo flow, integration |
| [Name 2] | Geospatial Engineer | Landsat, Sentinel-2, WorldCover, GHSL, OSM pipeline |
| [Name 3] | ML Engineer | XGBoost/RF models, SHAP, spatial cross-validation |
| [Name 4] | Full-stack Developer | FastAPI backend, Next.js dashboard, Deck.gl maps |
| [Name 5] | Data/Research | CPCB/IMD calibration, reports, validation, documentation |

## Slide 3 - Opportunity, Differentiation, USP

Indian cities face rising urban heat stress, but planners often receive only static heat maps. UrbanYantra converts satellite, morphology, weather, and planning data into a decision-support platform that answers three questions: where is the city hottest, why is it hot, and which intervention gives the best cooling return.

**How it is different from existing ideas**

Most solutions for this problem will likely create heat maps, train a model, and show generic cooling suggestions. UrbanYantra is different because it closes the full decision loop: sensing, explaining, simulating, ranking, and reporting.

- **Not just a heat map, but a heat decision engine:** UrbanYantra moves from "where is it hot?" to "why is it hot, what should be done, where should it be done first, and what cooling return can be expected?"
- **Driver-to-intervention bridge:** SHAP driver analysis is connected to action logic. For example, low NDVI points toward greening, high impervious/built-up areas point toward cool roofs, and water-deficit zones can be evaluated for blue infrastructure.
- **Physics-informed scenario evaluation:** The platform uses InVEST UCM-inspired cooling logic, a surrogate model, and a SOLWEIG-ready extension path, so interventions are not only ML predictions but scenario-based urban cooling decisions.
- **Planning-grade spatial output:** Landsat thermal data is downscaled toward 10 m using Sentinel-2 features, then connected to wards/grids, city boundaries, and local morphology so the output is usable for real planning units.
- **Spatially honest validation:** The model includes spatial cross-validation and leave-one-city-out benchmarking, reducing the common error of reporting high accuracy from random nearby pixels that leak spatial similarity.
- **Ground and data trust layer:** CPCB/IMD station calibration, dataset provenance, and the data audit API make the system transparent about which layers are real, cached, missing, or fallback.
- **Operational product, not only notebook output:** UrbanYantra has a FastAPI backend, Deck.gl dashboard, click-to-predict API, scenario comparison panel, ranked intervention sidebar, PDF report, and RAG chatbot.
- **Reusable multi-city engine:** The same pipeline supports multiple Indian cities, making it a scalable urban heat intelligence layer rather than a one-city demo.

**How it solves the problem**

- Detects ward/pixel-level hotspots at 10 m planning resolution.
- Explains heat drivers such as low vegetation, high built-up density, impervious surfaces, distance from water/green areas, and meteorological stress.
- Simulates cooling strategies including urban greening, cool roofs, green roofs, and blue infrastructure.
- Ranks top intervention zones using cooling potential, cost, feasibility, confidence, and ROI.
- Produces map layers, APIs, reports, and dashboards usable by planners and decision makers.

**USP**

UrbanYantra's core USP is that it transforms urban heat analysis from a diagnostic exercise into an investment-grade cooling decision system.

**Focused USP points**

- **Action-first heat intelligence:** Most tools stop at LST visualization. UrbanYantra produces a ranked cooling action plan with intervention type, location, expected temperature reduction, cost, feasibility, and confidence.
- **Explainability that directly guides mitigation:** The system does not simply say a location is hot. It explains whether the heat is caused by vegetation loss, impervious surface, built-up density, water distance, morphology, or weather stress, then links that evidence to the right intervention.
- **Physics-informed AI, not only black-box ML:** ML models predict LST and hotspots, while scenario simulation uses urban cooling logic inspired by InVEST UCM and is designed for SOLWEIG-based microclimate extension.
- **10 m planner-ready intelligence:** Landsat 8 thermal observations are downscaled using Sentinel-2 spectral features, creating outputs that are meaningful for wards, neighborhoods, and local intervention planning.
- **Trust and validation built in:** CPCB/IMD calibration, data provenance, model metrics, data audit, benchmarks, and spatial validation make the system defensible for government and planning use.
- **From city dashboard to decision API:** UrbanYantra is deployable as a working product, with interactive maps, click-to-predict, scenario comparison, report generation, chatbot support, and APIs for integration with municipal systems.
- **Scalable across Indian cities:** The pipeline is already structured for multi-city operation, allowing it to become a repeatable national urban heat mitigation framework.

**One-line USP for the slide**

UrbanYantra turns satellite heat data into explainable, physics-informed cooling investment decisions: where to intervene, why that place is hot, which solution fits, and what temperature reduction can be expected.

## Slide 4 - Features Offered By The Solution

**Recommended slide title:** One platform from satellite heat detection to cooling investment decisions

Instead of showing all features as a long list, present them as four visual capability pillars.

```text
+------------------------+------------------------+------------------------+------------------------+
| 1. Sense the city       | 2. Understand heat     | 3. Simulate cooling    | 4. Decide and report   |
+------------------------+------------------------+------------------------+------------------------+
| Landsat 8 LST          | Getis-Ord Gi* hotspots | Cool roofs             | Ranked top zones       |
| Sentinel-2 NDVI/NDBI   | XGBoost/RF prediction  | Urban greening         | Smart ROI scoring      |
| ESA WorldCover         | SHAP driver analysis   | Green roofs            | Dashboard + APIs       |
| GHSL + OSM + ERA5      | CPCB/IMD calibration   | Blue infrastructure    | PDF + RAG chatbot      |
+------------------------+------------------------+------------------------+------------------------+
```

**Feature highlights**

- Satellite heat intelligence: Landsat 8 LST ingestion, 10 m downscaling, Sentinel-2 NDVI/NDBI/NDWI/UTFVI, ESA WorldCover, GHSL, OSM, ERA5-Land/UTCI.
- AI hotspot analytics: Getis-Ord Gi*, XGBoost and Random Forest models, SHAP driver analysis, CPCB/IMD calibration, spatial leave-one-city-out validation.
- Cooling scenario engine: mitigation simulator, before/after comparison, AI cooling timeline, surrogate model, SOLWEIG-ready extension.
- Decision support: top-50 priority ranking, smart ROI scoring, multi-layer Deck.gl dashboard, click-to-predict map API, model metrics, data audit, climate, benchmark, and report APIs.
- Planner outputs: thermal satellite overlay, intervention sidebar, PDF report, RAG chatbot, and multi-city support.

**Visual suggestion for PPT**

Place a small map screenshot or thermal overlay in the center. Around it, add four labeled arrows:

```text
Satellite data -> AI heat diagnosis -> Cooling scenarios -> Ranked action plan
```

**Prototype proof point**

Mumbai output uses real satellite/GHSL/ERA5/OSM artifacts, 40 engineered features, 869,700 samples, XGBoost LST R2 of 0.929, MAE of 0.865 deg C, and hotspot accuracy of 99.6%.

## Slide 5 - Process Flow / Use Case Diagram

```text
User selects city
      |
      v
Satellite + weather + urban morphology ingestion
Landsat 8, Sentinel-2, WorldCover, GHSL, ERA5, OSM, CPCB/IMD
      |
      v
Pre-processing and feature table builder
10 m LST, NDVI, NDBI, NDWI, UTFVI, urban mask, wards, temporal features
      |
      v
AI/ML analytics
XGBoost/RF prediction, hotspot classification, SHAP driver attribution
      |
      v
Scenario simulator
Cool roofs, green roofs, urban greening, blue infrastructure, budget/ROI
      |
      v
Decision outputs
Heatmap layers, ranked interventions, before/after map, PDF report, chatbot
```

**Primary use case**

1. Urban planner selects a city and heatmap layer.
2. Dashboard shows hotspot intensity, driver layers, and ward/grid statistics.
3. Planner clicks a point/ward to get predicted LST and hotspot risk.
4. Planner adjusts mitigation strategy and budget.
5. System compares scenarios and recommends high-priority cooling zones.
6. Planner downloads a PDF report or asks the chatbot for city-specific insights.

## Slide 6 - Wireframes / Mock Diagrams

**Dashboard layout**

```text
+--------------------------------------------------------------------------------+
| Header: City, baseline LST, scenario LST, investment, CO2, heat-stress metrics   |
+----------------------+--------------------------------------+------------------+
| Cooling Simulator    | Interactive Deck.gl Map              | Insights Panel   |
| - Target ward        | - LST / NDVI / Gi* / NDBI layers      | - Top drivers    |
| - Cool roofs %       | - Satellite basemap toggle            | - Interventions  |
| - Green roofs %      | - Thermal overlay                     | - Climate trend  |
| - Urban greening %   | - Click-to-predict popup              | - Data audit     |
| - Blue infra %       | - Before/after slider                 |                  |
+----------------------+--------------------------------------+------------------+
| Scenario comparison panel: ROI, cooling, cost, population benefited, smart pick  |
+--------------------------------------------------------------------------------+
| Floating AI chatbot: explain heat drivers, interventions, and data status        |
+--------------------------------------------------------------------------------+
```

**Important UI screens**

- Multi-city landing dashboard with city selector.
- Multi-layer map: LST, NDVI, NDBI, NDWI, Gi*, GHSL, risk, thermal satellite.
- Scenario comparison panel with smart suggestions.
- AI cooling timeline: 6 months, 1 year, 3 years, 10 years.
- Ranked interventions sidebar and data status/audit modal.
- PDF report download and RAG chatbot.

## Slide 7 - Architecture Diagram

```text
Data Sources
  Landsat 8 | Sentinel-2 | ESA WorldCover | GHSL | ERA5-Land/UTCI | OSM | CPCB/IMD
      |
      v
Ingestion Layer
  GEE export pipeline | remote cache | local raster loaders | provenance tracker
      |
      v
Geospatial Processing Layer
  10 m LST downscaling | spectral indices | urban mask | morphology | ward stats
      |
      v
Feature and Modeling Layer
  feature table | XGBoost | Random Forest | hotspot classifier | spatial CV | SHAP
      |
      v
Simulation and Decision Layer
  cooling scenarios | surrogate model | SOLWEIG stub | ROI scoring | top rankings
      |
      v
Backend API - FastAPI
  city summary | heatmaps | prediction | scenario | benchmarks | report | chat
      |
      v
Frontend - Next.js + Deck.gl
  maps | before/after slider | scenario panel | timeline | audit panel | chatbot
```

## Slide 8 - Technologies To Be Used

**Geospatial and data**

- Google Earth Engine for Landsat 8, Sentinel-2, ESA WorldCover, ERA5-Land.
- GHSL built-up, SMOD, and population layers through cache/local variants.
- OpenStreetMap, OSMnx, GeoPandas, Shapely, Rasterio, Rioxarray, Xarray, PyProj.
- Hugging Face dataset cache for large static urban datasets.

**AI/ML**

- XGBoost, Random Forest, scikit-learn, SciPy, NumPy, Pandas.
- SHAP for explainable AI.
- Spatial cross-validation and leave-one-city-out validation.
- Surrogate model and SOLWEIG-ready extension point.

**Backend and APIs**

- Python FastAPI, Uvicorn, Pydantic.
- REST APIs for cities, heatmaps, hotspots, prediction, scenario comparison, reports, data audit, metrics, benchmarks, and chatbot.
- ReportLab for PDF report generation.

**Frontend and visualization**

- Next.js, React, TypeScript, Tailwind CSS.
- Deck.gl, MapLibre, React Map GL, Leaflet, Recharts.
- Carto and ESRI satellite basemap toggle.

**Deployment**

- Render for FastAPI backend.
- Vercel for frontend.
- Precomputed outputs and cache layer for hackathon-scale reliability.

## Slide 9 - Estimated Implementation Cost

**Prototype / hackathon stage**

- Software stack: open source.
- Satellite/public data: mostly free through GEE, GHSL, ESA, ERA5, OSM, CPCB/IMD references.
- Cloud demo: low-cost/free-tier Render + Vercel for frontend/backend.
- Main cost: compute time, storage for rasters/models, and team effort.

**Indicative deployment cost**

| Cost head | Estimate |
| --- | --- |
| Cloud hosting and storage for 10-city pilot | INR 5,000-25,000 per month, depending on traffic and retained rasters |
| Production GEE/data processing and storage | INR 25,000-1,00,000 per month if scaled to many cities with frequent refresh |
| City-level calibration/validation | Depends on station access and field validation support |
| Dashboard/API maintenance | Depends on SLA, update frequency, and integrations |

**Intervention cost assumptions used by simulator**

| Intervention | Cost assumption |
| --- | --- |
| Cool roofs | INR 450 per sq m |
| Urban greening | INR 1,200 per sq m |
| Blue infrastructure | INR 3,500 per sq m |

## Slide 10 - Closing / Expected Impact

UrbanYantra helps cities shift from reactive heat response to data-backed cooling investment.

**Expected impact**

- Faster identification of high-risk heat zones.
- Transparent evidence for why each zone is hot.
- Better allocation of limited urban cooling budgets.
- Ward-level and pixel-level recommendations for greening, cool roofs, and blue infrastructure.
- Reusable national platform across Indian cities.

**Current readiness**

- Multi-city prototype implemented.
- Real-data pipeline and cache layer available.
- Interactive dashboard and FastAPI backend implemented.
- AI prediction, SHAP explainability, scenario comparison, PDF report, and chatbot implemented.

**Ask**

Support validation with municipal datasets, CPCB/IMD station access, GEE production access, and pilot deployment with city planning agencies.
