# Cloud Deployment — Hugging Face + Vercel (recommended)

## Architecture

| Tier | Platform | Role |
|------|----------|------|
| Storage | HF Dataset `karthikj30/UrbanYantra-outputs` | Precomputed `outputs/` (~500 MB–2 GB, all cities) |
| Raw data | HF Dataset `sleepingbeauty11/UrbanDatasets` | GHSL + ERA5 (17 GB — local pipeline only) |
| API | HF Space `karthikj30/urbanyantra-api` | FastAPI + XGBoost + rasterio (16 GB RAM free) |
| Frontend | Vercel | Next.js — `NEXT_PUBLIC_API_BASE` → HF Space |

## Quick deploy

```powershell
hf auth login
.\scripts\deploy_all.ps1
```

Then create HF Space + Vercel per `README.md` deploy section.

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | HF Space container build |
| `entrypoint.sh` | Sync outputs from HF → start uvicorn |
| `scripts/upload_outputs_to_hf.py` | Push `outputs/` to HF Dataset |
| `scripts/sync_outputs_from_hf.py` | Pull outputs on Space startup |
| `configs/deploy.yaml` | Repo IDs and Space name |
| `vercel.json` | Vercel frontend + API URL |

## HF Space secrets

| Variable | Value |
|----------|-------|
| `HF_OUTPUTS_REPO` | `karthikj30/UrbanYantra-outputs` |
| `CORS_ALLOW_ORIGINS` | `https://your-app.vercel.app` |
| `OPENROUTER_API_KEY` | Optional |

## Fallback: Render

See `render.yaml` — bundles `outputs/` in Git instead of HF sync.
