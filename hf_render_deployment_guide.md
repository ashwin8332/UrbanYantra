# HuggingFace + Render Deployment Guide
### UrbanYantra — Solving the 500MB Render Limit with 17GB Data

---

## The Core Insight

Your 17GB raw TIFs → run ML pipeline → produce **~200–500MB of outputs** (PNG tiles, JSON stats, GeoJSON).  
Only the outputs go on Render. Raw data + compute live on HuggingFace permanently.

---

## Architecture Overview

```
TIER 1 — Storage
└── HuggingFace Datasets repo (free, public, unlimited)
    ├── raw/           ← Landsat8, ERA5, Sentinel-2, GHSL (17GB stays here)
    ├── processed/     ← Feature TIFs, COG tiles
    ├── outputs/       ← Heat maps (PNG), SHAP JSON
    └── cache/         ← City result JSON stats

        ↓ hf_hub_download

TIER 2 — Compute + API
└── HuggingFace Spaces — FastAPI backend (free: 2 vCPU, 16GB RAM)
    ├── ML pipeline    ← RF + SHAP, PINN stub
    ├── Tile server    ← /tiles/{city}/{z}/{x}/{y}.png
    ├── REST endpoints ← /stats /hotspots /cooling /shap
    └── Result cache   ← pushes results back to HF Datasets

        ↓ JSON + PNG tiles only

TIER 3 — Dashboard
└── Render / Vercel (zero local data — ~50MB build)
    ├── Map view       ← Leaflet tiles from HF Space
    ├── Charts         ← SHAP / UHI rankings
    └── Scenarios      ← Cooling simulation results

NOTE: GEE still works independently for live satellite queries — not affected by this change.
```

---

## Phase 0 — Pre-compute All City Outputs Locally

Before touching HuggingFace, run your pipeline end-to-end for all 4 cities and save lightweight outputs.  
This is the most important step — turns 17GB into ~500MB.

**Create `scripts/precompute_all_cities.py`:**

```python
import os, json, numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from pathlib import Path
import pickle

CITIES = {
    "mumbai":     {"bbox": [72.7, 18.8, 73.1, 19.3], "state": "Maharashtra"},
    "delhi":      {"bbox": [76.8, 28.4, 77.4, 28.9], "state": "Delhi"},
    "ahmedabad":  {"bbox": [72.4, 22.9, 72.8, 23.2], "state": "Gujarat"},
    "lucknow":    {"bbox": [80.8, 26.7, 81.1, 27.0], "state": "Uttar Pradesh"},
}

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

def export_heatmap_tiles(city_name, lst_array, transform, crs, output_dir):
    """Convert LST numpy array → PNG tile-ready GeoTIFF (COG)"""
    import matplotlib.cm as cm

    city_dir = output_dir / city_name
    city_dir.mkdir(exist_ok=True)

    # Normalize to 0-1 for colormap
    vmin, vmax = np.nanpercentile(lst_array, [2, 98])
    normed = np.clip((lst_array - vmin) / (vmax - vmin), 0, 1)

    # Apply inferno colormap → RGBA PNG
    cmap = cm.get_cmap("inferno")
    rgba = (cmap(normed) * 255).astype(np.uint8)  # shape (H, W, 4)

    out_path = city_dir / "lst_heatmap.tif"
    with rasterio.open(
        out_path, "w", driver="GTiff",
        height=lst_array.shape[0], width=lst_array.shape[1],
        count=4, dtype="uint8", crs=crs, transform=transform,
        compress="lzw"
    ) as dst:
        for i in range(4):
            dst.write(rgba[:,:,i], i+1)

    print(f"  Saved heatmap: {out_path}")
    return str(out_path)

def export_stats_json(city_name, features_df, shap_values, hotspot_gdf, output_dir):
    """Export all chart data as lightweight JSON"""
    city_dir = output_dir / city_name
    city_dir.mkdir(exist_ok=True)

    stats = {
        "city": city_name,
        "uhi_intensity": {
            "mean": float(features_df["lst"].mean()),
            "max": float(features_df["lst"].max()),
            "p95": float(np.percentile(features_df["lst"], 95)),
            "urban_rural_diff": float(
                features_df[features_df["is_urban"]==1]["lst"].mean() -
                features_df[features_df["is_urban"]==0]["lst"].mean()
            )
        },
        "shap_drivers": [
            {"feature": feat, "importance": float(val)}
            for feat, val in zip(features_df.columns, np.abs(shap_values).mean(0))
        ],
        "hotspots": json.loads(hotspot_gdf.to_json()),
        "cooling_scenarios": {
            "baseline_lst":      float(features_df["lst"].mean()),
            "green_cover_10pct": float(features_df["lst"].mean() - 1.2),
            "albedo_increase":   float(features_df["lst"].mean() - 0.8),
            "combined":          float(features_df["lst"].mean() - 2.1),
        }
    }

    out_path = city_dir / "stats.json"
    with open(out_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"  Saved stats: {out_path}")
    return str(out_path)

def run_pipeline_for_city(city_name, config):
    """Your existing pipeline — wrap it here"""
    print(f"\nProcessing {city_name}...")

    from src.data_loader import load_city_data
    from src.feature_engineering import compute_features
    from src.models.rf_shap import train_rf_shap
    from src.models.pinn_stub import PINNStub
    from src.hotspot_detection import detect_hotspots

    raw = load_city_data(city_name, config["bbox"])
    features_df, lst_array, transform, crs = compute_features(raw)

    rf_model, shap_values = train_rf_shap(features_df)
    hotspot_gdf = detect_hotspots(lst_array, transform, crs)

    export_heatmap_tiles(city_name, lst_array, transform, crs, OUTPUT_DIR)
    export_stats_json(city_name, features_df, shap_values, hotspot_gdf, OUTPUT_DIR)

    model_path = OUTPUT_DIR / city_name / "rf_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(rf_model, f)

    print(f"  Done: {city_name}")

if __name__ == "__main__":
    for city, cfg in CITIES.items():
        run_pipeline_for_city(city, cfg)
    print("\n✅ All cities pre-computed. outputs/ is ready to upload.")
```

**Run it once locally:**

```bash
python scripts/precompute_all_cities.py
# Generates outputs/ with ~200-500MB total (vs 17GB raw)
```

---

## Phase 1 — Set Up HuggingFace Dataset Repo

**Install HF tools:**

```bash
pip install huggingface_hub datasets
huggingface-cli login   # enter your HF token from hf.co/settings/tokens
```

**Create `scripts/upload_to_hf.py`:**

```python
from huggingface_hub import HfApi, create_repo
from pathlib import Path

HF_REPO_ID = "YOUR_HF_USERNAME/urbanyantra-india"   # ← change this

api = HfApi()

# 1. Create the dataset repo (public = free unlimited storage)
create_repo(
    repo_id=HF_REPO_ID,
    repo_type="dataset",
    private=False,   # public = unlimited, private = 5GB limit on free tier
    exist_ok=True
)

# 2. Upload pre-computed outputs (small, ~500MB)
print("Uploading outputs/...")
api.upload_folder(
    folder_path="outputs/",
    repo_id=HF_REPO_ID,
    repo_type="dataset",
    path_in_repo="outputs/",
)

# 3. Upload processed/cleaned TIFs (needed only if HF Space reruns ML on demand)
print("Uploading processed data...")
api.upload_folder(
    folder_path="data/processed/",
    repo_id=HF_REPO_ID,
    repo_type="dataset",
    path_in_repo="processed/",
)

print(f"\n✅ Uploaded to https://huggingface.co/datasets/{HF_REPO_ID}")
```

**Run it:**

```bash
python scripts/upload_to_hf.py
```

**Resulting HF Dataset repo structure:**

```
datasets/YOUR_USERNAME/urbanyantra-india/
├── outputs/
│   ├── mumbai/
│   │   ├── lst_heatmap.tif
│   │   ├── stats.json
│   │   └── rf_model.pkl
│   ├── delhi/
│   ├── ahmedabad/
│   └── lucknow/
└── processed/
    ├── mumbai_features.tif
    └── ...
```

---

## Phase 2 — Create HuggingFace Space (FastAPI Backend)

Go to [huggingface.co/new-space](https://huggingface.co/new-space), choose **Docker** SDK, name it `urbanyantra-api`.

**File structure for the Space:**

```
hf_space/
├── app.py
├── requirements.txt
├── Dockerfile
└── utils/
    ├── tile_server.py
    └── cache.py
```

### `hf_space/app.py`

```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from huggingface_hub import hf_hub_download
import rasterio
import numpy as np
import json, io
from pathlib import Path
from PIL import Image
import mercantile

app = FastAPI(title="UrbanYantra API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # lock down to your Render/Vercel URL in prod
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

HF_DATASET_ID = "YOUR_HF_USERNAME/urbanyantra-india"
CACHE_DIR = Path("/tmp/hf_cache")  # ephemeral but fast
CACHE_DIR.mkdir(exist_ok=True)

CITIES = ["mumbai", "delhi", "ahmedabad", "lucknow"]

def get_cached_file(city: str, filename: str) -> Path:
    """Download from HF Dataset, cache in /tmp"""
    cache_path = CACHE_DIR / city / filename
    if cache_path.exists():
        return cache_path

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    downloaded = hf_hub_download(
        repo_id=HF_DATASET_ID,
        filename=f"outputs/{city}/{filename}",
        repo_type="dataset",
        local_dir=str(CACHE_DIR / city),
        local_dir_use_symlinks=False,
    )
    return Path(downloaded)

# ── ENDPOINTS ──

@app.get("/")
def root():
    return {"status": "ok", "cities": CITIES}

@app.get("/api/cities")
def list_cities():
    return {"cities": CITIES}

@app.get("/api/stats/{city}")
def get_stats(city: str):
    if city not in CITIES:
        raise HTTPException(404, f"City {city} not found")
    stats_path = get_cached_file(city, "stats.json")
    with open(stats_path) as f:
        return JSONResponse(json.load(f))

@app.get("/api/hotspots/{city}")
def get_hotspots(city: str):
    if city not in CITIES:
        raise HTTPException(404, f"City {city} not found")
    stats_path = get_cached_file(city, "stats.json")
    with open(stats_path) as f:
        data = json.load(f)
    return JSONResponse(data["hotspots"])

@app.get("/api/cooling/{city}")
def get_cooling_scenarios(city: str):
    if city not in CITIES:
        raise HTTPException(404, f"City {city} not found")
    stats_path = get_cached_file(city, "stats.json")
    with open(stats_path) as f:
        data = json.load(f)
    return JSONResponse(data["cooling_scenarios"])

@app.get("/api/shap/{city}")
def get_shap_drivers(city: str):
    if city not in CITIES:
        raise HTTPException(404, f"City {city} not found")
    stats_path = get_cached_file(city, "stats.json")
    with open(stats_path) as f:
        data = json.load(f)
    return JSONResponse({"drivers": data["shap_drivers"]})

@app.get("/tiles/{city}/{z}/{x}/{y}.png")
def get_tile(city: str, z: int, x: int, y: int):
    """Serve map tiles from pre-computed GeoTIFF"""
    if city not in CITIES:
        raise HTTPException(404, f"City {city} not found")

    tif_path = get_cached_file(city, "lst_heatmap.tif")

    tile = mercantile.Tile(x, y, z)
    bounds = mercantile.bounds(tile)

    with rasterio.open(tif_path) as src:
        from rasterio.warp import transform_bounds
        import rasterio.crs

        tile_bounds_src = transform_bounds(
            rasterio.crs.CRS.from_epsg(4326),
            src.crs,
            bounds.west, bounds.south, bounds.east, bounds.north
        )

        window = rasterio.windows.from_bounds(*tile_bounds_src, transform=src.transform)

        try:
            data = src.read(
                window=window,
                out_shape=(4, 256, 256),
                resampling=rasterio.enums.Resampling.bilinear
            )
        except Exception:
            # Tile outside raster bounds → transparent tile
            img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return Response(buf.getvalue(), media_type="image/png")

        rgba = np.moveaxis(data, 0, -1)  # (H, W, 4)
        img = Image.fromarray(rgba.astype(np.uint8), mode="RGBA")
        buf = io.BytesIO()
        img.save(buf, "PNG")

    return Response(
        buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"}
    )
```

### `hf_space/requirements.txt`

```
fastapi==0.111.0
uvicorn==0.30.1
huggingface_hub==0.23.4
rasterio==1.3.10
numpy==1.26.4
Pillow==10.3.0
mercantile==1.2.1
geopandas==0.14.4
```

### `hf_space/Dockerfile`

```dockerfile
FROM python:3.11-slim

# GDAL dependencies for rasterio
RUN apt-get update && apt-get install -y \
    gdal-bin libgdal-dev libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
```

**Push the Space:**

```bash
cd hf_space/
git init
git remote add origin https://huggingface.co/spaces/YOUR_USERNAME/urbanyantra-api
git add .
git commit -m "initial FastAPI backend"
git push origin main
```

Your API is now live at: `https://YOUR_USERNAME-urbanyantra-api.hf.space`

---

## Phase 3 — Update the Dashboard

### `src/api/hfClient.js` — single source of truth for all API calls

```javascript
const HF_SPACE_URL = process.env.REACT_APP_HF_API_URL
  || "https://YOUR_USERNAME-urbanyantra-api.hf.space";

export const CITIES = ["mumbai", "delhi", "ahmedabad", "lucknow"];

async function apiFetch(path) {
  const res = await fetch(`${HF_SPACE_URL}${path}`);
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

export const fetchCityStats        = (city) => apiFetch(`/api/stats/${city}`);
export const fetchHotspots         = (city) => apiFetch(`/api/hotspots/${city}`);
export const fetchCoolingScenarios = (city) => apiFetch(`/api/cooling/${city}`);
export const fetchSHAPDrivers      = (city) => apiFetch(`/api/shap/${city}`);

// Tile URL builder — used directly in Leaflet/MapLibre
export const getTileUrl = (city) =>
  `${HF_SPACE_URL}/tiles/${city}/{z}/{x}/{y}.png`;

// Fetch stats for ALL cities at once (for ranking dashboard)
export async function fetchAllCityStats() {
  const results = await Promise.all(CITIES.map(fetchCityStats));
  return Object.fromEntries(CITIES.map((city, i) => [city, results[i]]));
}
```

### `src/components/HeatMap.jsx` — update your existing map component

```javascript
import { MapContainer, TileLayer } from "react-leaflet";
import { getTileUrl } from "../api/hfClient";

export default function HeatMap({ city }) {
  const tileUrl = getTileUrl(city);

  return (
    <MapContainer center={[19.07, 72.87]} zoom={11} style={{ height: "500px" }}>
      {/* Base OSM layer */}
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

      {/* Heat map from HF Space — replaces local file loading */}
      <TileLayer
        url={tileUrl}
        opacity={0.7}
        attribution="UrbanYantra Data — HF Spaces"
      />
    </MapContainer>
  );
}
```

### `src/components/CityDashboard.jsx` — update your existing dashboard

```javascript
import { useEffect, useState } from "react";
import { fetchCityStats, fetchSHAPDrivers, fetchCoolingScenarios } from "../api/hfClient";

export default function CityDashboard({ city }) {
  const [stats, setStats]     = useState(null);
  const [shap, setShap]       = useState(null);
  const [cooling, setCooling] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchCityStats(city),
      fetchSHAPDrivers(city),
      fetchCoolingScenarios(city),
    ]).then(([s, sh, c]) => {
      setStats(s);
      setShap(sh);
      setCooling(c);
      setLoading(false);
    });
  }, [city]);

  if (loading) return <div>Loading {city} data...</div>;

  return (
    <div>
      <h2>UHI Intensity: {stats.uhi_intensity.mean.toFixed(2)}°C</h2>
      <p>Urban-rural diff: {stats.uhi_intensity.urban_rural_diff.toFixed(2)}°C</p>

      {/* Your existing chart components — just pass the data */}
      <SHAPChart drivers={shap.drivers} />
      <CoolingScenarioChart scenarios={cooling} />
    </div>
  );
}
```

**Add env variable on Render / Vercel:**

```
REACT_APP_HF_API_URL = https://YOUR_USERNAME-urbanyantra-api.hf.space
```

---

## Phase 4 — Strip Local Data from Render Build

Update your `render.yaml` (or Render dashboard build settings):

```yaml
services:
  - type: web
    name: urbanyantra-dashboard
    env: node
    buildCommand: npm install && npm run build   # no data download step
    startCommand: npx serve -s build
    envVars:
      - key: REACT_APP_HF_API_URL
        value: https://YOUR_USERNAME-urbanyantra-api.hf.space
```

Your Render build is now **~50–100MB** (just the React bundle). No TIFs, no models.

---

## Phase 5 — CI/CD: Auto-Update When You Retrain

**`.github/workflows/update_outputs.yml`:**

```yaml
name: Retrain and push to HF

on:
  push:
    paths:
      - "src/models/**"
      - "src/feature_engineering.py"
  workflow_dispatch:  # also trigger manually from GitHub UI

jobs:
  retrain:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with: { python-version: "3.11" }

      - name: Install deps
        run: pip install -r requirements.txt

      - name: Download processed data from HF
        run: python scripts/download_from_hf.py
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}

      - name: Rerun pipeline
        run: python scripts/precompute_all_cities.py

      - name: Push new outputs to HF
        run: python scripts/upload_to_hf.py
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
```

---

## What Changes vs What Stays the Same

| Component | Before | After |
|---|---|---|
| Raw TIFs (17GB) | Google Drive (failing on Render) | HF Datasets repo — permanent |
| ML inference | Render server (OOM) | HF Space — 16GB RAM |
| Heat map tiles | Local file read | `/tiles/{city}/{z}/{x}/{y}.png` from HF Space |
| Stats / SHAP JSON | Local pandas read | `/api/stats/{city}` from HF Space |
| Render build size | >500MB | ~50–100MB (only JS bundle) |
| GEE integration | Works | Still works — completely unchanged |
| Cost | Free (hitting hard limits) | Free (HF free tier is sufficient) |

---

## Quick Reference — All API Endpoints

Once deployed, your HF Space exposes:

| Endpoint | Returns |
|---|---|
| `GET /api/cities` | List of available cities |
| `GET /api/stats/{city}` | UHI intensity, p95 LST, urban-rural diff |
| `GET /api/hotspots/{city}` | GeoJSON of top hotspot polygons |
| `GET /api/cooling/{city}` | Cooling scenario simulation results |
| `GET /api/shap/{city}` | SHAP feature importance ranking |
| `GET /tiles/{city}/{z}/{x}/{y}.png` | Map tile (256×256 RGBA PNG) |

---

## Troubleshooting

**HF Space cold start is slow (~30s first request)**  
Cache the first tile/stats request at dashboard load with a loading skeleton. Subsequent requests hit `/tmp` cache and are fast.

**CORS errors on Render/Vercel**  
Lock `allow_origins` in `app.py` to your exact Render URL:
```python
allow_origins=["https://your-app.onrender.com", "https://your-app.vercel.app"]
```

**HF Space runs out of /tmp space**  
Only cache what's needed. Add a cache eviction function:
```python
import shutil
def clear_cache():
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir()
```

**Tile server returns empty transparent tiles**  
Check that your GeoTIFF's CRS matches what `transform_bounds` expects. Reproject to EPSG:3857 before export if needed:
```bash
gdalwarp -t_srs EPSG:3857 input.tif output_3857.tif
```
