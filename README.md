# Optimizing Urban Heat Mitigation via AI/ML (UrbanYantra)

End-to-end ISRO hackathon prototype: **hotspot detection**, **SHAP driver attribution**, **GHSL/ERA5 real-data layers**, **live XGBoost inference**, and **cooling scenario simulation** with ranked interventions.

## Stack

| Layer | Tools |
|-------|-------|
| LST | Landsat 8 C2 L2 via GEE |
| 10 m downscaling | Sentinel-2 NDVI/NDBI regression |
| LULC | ESA WorldCover 10 m |
| Meteo / heat stress | ERA5 UTCI (Hugging Face cache) or ERA5-Land (GEE) |
| Morphology | GHSL Built-S, SMOD, population (Hugging Face cache) + OSM |
| ML | XGBoost + Random Forest + spatial CV |
| External benchmarks | D-07 Kaggle UHI CSV, D-09 EY NYC labels |
| Explainability | SHAP |
| Scenarios | InVEST UCM-inspired ΔT + surrogate model |
| Dashboard | Next.js + Deck.gl map + FastAPI backend |

---

## Quick start (local)

```powershell
# 1. Python environment
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. Run pipeline on one city (real data from Hugging Face + GEE satellite)
py run_pipeline.py --city Mumbai --data-mode local --force

# 3. Start API
uvicorn backend.app.main:app --reload --port 8000

# 4. Start frontend (new terminal)
cd frontend
copy .env.example .env.local
npm install
npm run dev
# Open http://localhost:3000
```

**Port 8000 busy?** Use `--port 8001` and set `NEXT_PUBLIC_API_BASE=http://localhost:8001` in `frontend/.env.local`.

---

## Download real data (Hugging Face)

Urban datasets are hosted on Hugging Face (replaces Google Drive — no 4-folder sync limit):

```
https://huggingface.co/datasets/sleepingbeauty11/UrbanDatasets
→ configs/remote_datasets.yaml → urban_dataset_folder.huggingface_repo_id
```

### What gets downloaded (first pipeline run)

| Dataset | ID | Cache path | Used for |
|---------|-----|------------|----------|
| GHSL Built-S | D-04 | `data/cache/urban_dataset/ghsl/` (7 India zips) | Built-up density map layer |
| GHSL SMOD | D-04 | same folder | Settlement / urban-core map layer |
| GHSL Population | D-04 | clipped rasters in `outputs/{city}/rasters/` | Population exposure layer |
| ERA5 UTCI NetCDF | D-03 | `data/cache/urban_dataset/era5/` | Heat-stress / meteo features |
| Kaggle UHI CSV | D-07 | `data/benchmarks/` (bundled in Git) | Training benchmark |
| EY NYC UHI labels | D-09 | `data/benchmarks/` (bundled in Git) | External validation benchmark |

### Download commands

```powershell
pip install huggingface_hub   # one-time, for dataset sync

# Single city — auto-syncs Hugging Face on first run, then uses cache
py run_pipeline.py --city Mumbai --data-mode local --force

# All 10 configured cities
py run_pipeline.py --multi-city --data-mode local --force
```

**Repo must be public** (or set `HF_TOKEN` env var for private repos).

**Local PC shortcut:** You can also point to extracted files in `configs/local_datasets.yaml` (see `docs/REAL_DATA_GUIDE.md`).

---

## Data modes

| Mode | GHSL / ERA5 | Satellite (LST, S2, WorldCover) |
|------|-------------|-----------------------------------|
| `local` | Hugging Face cache | GEE |
| `gee` | GEE or Hugging Face if configured | GEE |
| `synthetic` | Synthetic fallback | Synthetic fallback |

Recommended for hackathon demo: **`local`** (real GHSL + ERA5 from Hugging Face, real Landsat from GEE).

The dashboard shows **"Error fetching data"** (not "Live outputs") when any critical artifact is missing — GHSL, ERA5, Landsat, WorldCover, or Sentinel-2.

---

## Pipeline outputs (`outputs/{city}/`)

| Path | Description |
|------|-------------|
| `tables/feature_table.parquet` | Pixel features + USP columns |
| `tables/intervention_rankings.csv` | Ranked cooling zones (real InVEST UCM ΔT) |
| `ranking/{city}.json` | Same rankings for API |
| `rasters/ghsl_built_surface.tif` | GHSL built-up layer for map |
| `rasters/ghsl_smod.tif` | GHSL settlement layer for map |
| `models/xgb_lst_regressor.joblib` | Live inference model |
| `models/benchmark_metrics.json` | City XGBoost + Kaggle/EY baselines |
| `benchmarks/` | D-07/D-09 summaries |
| `maps/thermal_satellite.png` | Landsat thermal overlay |
| `geojson/hotspots_*.geojson` | Hotspot pin locations |
| `summary.json` | Provenance manifest for dashboard |

---

## Dashboard map layers

| Layer | Source |
|-------|--------|
| Surface Temperature | Landsat LST (10 m downscaled) |
| Thermal View | Raw Landsat ST_B10 on satellite basemap |
| Heat Stress (UTCI) | ERA5 UTCI + LST proxy |
| Green Coverage (NDVI) | Sentinel-2 |
| GHSL Built-up | GHSL Built-S (Hugging Face cache) |
| GHSL Population | GHSL population raster |
| GHSL Settlement (SMOD) | GHSL SMOD settlement degree |
| Risk Level | Hotspot class + LST composite |
| Heat hotspots (pins) | Getis-Ord Gi* severe/moderate pixels |

Right panel: **Ranked Interventions** (top zones per strategy from real LST/NDVI rasters), SHAP drivers, cooling potential, climate trend.

---

## Deploy to Hugging Face + Vercel (recommended — free tier, all 10 cities)

Architecture: **HF Datasets = outputs storage** · **HF Space = FastAPI API** · **Vercel = Next.js frontend**

Raw 17 GB GHSL/ERA5 stays on [UrbanDatasets](https://huggingface.co/datasets/sleepingbeauty11/UrbanDatasets).  
Precomputed `outputs/` uploads to your HF Dataset; the Space syncs them at startup (no Render 500 MB limit).

### One-command deploy helper

```powershell
hf auth login
.\scripts\deploy_all.ps1
```

### Manual steps

**1. Precompute locally (if needed)**

```powershell
py run_pipeline.py --multi-city --data-mode local --force
```

**2. Upload outputs to Hugging Face**

```powershell
py scripts/upload_outputs_to_hf.py
```

Repo ID is in `configs/deploy.yaml` (default: `karthikj30/UrbanYantra-outputs`). Create a **public** dataset at [huggingface.co/new-dataset](https://huggingface.co/new-dataset) first.

**3. Create HF Space (Docker backend)**

- [huggingface.co/new-space](https://huggingface.co/new-space) → SDK: **Docker** → connect `karthikj30/UrbanYantra` GitHub repo
- Uses root `Dockerfile` + `entrypoint.sh`
- Space secrets: `HF_OUTPUTS_REPO`, `CORS_ALLOW_ORIGINS` (your Vercel URL), optional `OPENROUTER_API_KEY`
- API URL: `https://karthikj30-urbanyantra-api.hf.space`

**4. Deploy frontend on Vercel**

```powershell
# Env var in Vercel dashboard:
NEXT_PUBLIC_API_BASE=https://karthikj30-urbanyantra-api.hf.space
```

Root `vercel.json` and `frontend/.env.example` already default to the HF Space URL.

### Verify

```powershell
curl https://karthikj30-urbanyantra-api.hf.space/
curl https://karthikj30-urbanyantra-api.hf.space/cities
curl https://karthikj30-urbanyantra-api.hf.space/cities/Mumbai/summary
```

See also: `hf_render_deployment_guide.md`, `hf_space/README.md`, `docs/CLOUD_DEPLOY.md`.

### Fallback: Render backend

`render.yaml` remains available if you prefer Render over HF Space for the API.

---

## API endpoints (selected)

| Endpoint | Description |
|----------|-------------|
| `GET /cities` | List cities with data |
| `GET /cities/{city}/summary` | Metrics + provenance (includes `fetch_errors` if any) |
| `GET /cities/{city}/data-audit` | Per-dataset status (`error` when fetch failed) |
| `GET /cities/{city}/wards` | 3-D map grid GeoJSON |
| `GET /cities/{city}/heatmap/{layer}/meta` | Layer bounds (incl. `ghsl_built`, `ghsl_population`, `ghsl_smod`) |
| `GET /cities/{city}/hotspots` | Hotspot pin GeoJSON |
| `GET /cities/{city}/interventions` | Ranked intervention table |
| `GET /cities/{city}/benchmarks` | D-07/D-09 + training pipeline metrics |
| `POST /predict/point` | Live XGBoost LST + hotspot |
| `POST /scenario` | Cooling simulator |

Full docs: `http://localhost:8000/docs`

---

## Multi-city run

```powershell
py run_pipeline.py --multi-city --data-mode local --cities Mumbai Pune Delhi_NCR Bengaluru Chennai Kolkata Hyderabad Visakhapatnam Ahmedabad Mangaluru
```

---

## Tests

```powershell
pytest tests/ -q
cd frontend && npx tsc --noEmit
```

---

## Docs

| File | Contents |
|------|----------|
| `docs/REAL_DATA_GUIDE.md` | Wiring GHSL, ERA5, GEE |
| `docs/CLOUD_DEPLOY.md` | Render/Vercel details |
| `docs/RUNBOOK.md` | Operational runbook |
| `docs/HACKATHON_NARRATIVE.md` | Pitch narrative |

---

## References
- [Hugging Face Datasets](https://huggingface.co/datasets/sleepingbeauty11/UrbanDatasets/tree/main)
- [Hugging Face Datasets Output](https://huggingface.co/datasets/sleepingbeauty11/UrbanYantra-outputs/tree/main)
- [Hugging Face space](https://huggingface.co/spaces/sleepingbeauty11/urbanyantra-api?logs=container)
- [UHI-Analysis](https://github.com/ArhamOrioner/UHI-Analysis) — GEE + ML hotspot pipeline
- [WRI UrbanHeatMitigation](https://github.com/wri/UrbanHeatMitigation)
- [InVEST UCM calibration](https://github.com/martibosch/invest-ucm-calibration)
- [UrbanDatasets on Hugging Face](https://huggingface.co/datasets/sleepingbeauty11/UrbanDatasets)
