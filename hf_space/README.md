---
title: UrbanYantra API
emoji: 🌡️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# UrbanYantra API (FastAPI)

Backend for the Urban Heat Mitigation dashboard. Serves precomputed city outputs synced from Hugging Face Datasets at startup.

**Monorepo deploy:** connect this GitHub repo to the Space; the root `Dockerfile` and `entrypoint.sh` are used automatically.

## Space secrets (Settings → Variables and secrets)

| Key | Value |
|-----|-------|
| `HF_OUTPUTS_REPO` | `sleepingbeauty11/UrbanYantra-outputs` |
| `CORS_ALLOW_ORIGINS` | `https://urban-yantra.vercel.app` |
| `OPENROUTER_API_KEY` | Your OpenRouter key (for AI chat) |
| `APP_PUBLIC_URL` | `https://urban-yantra.vercel.app` |

## Health check

```
GET /
GET /cities
GET /cities/Mumbai/summary
```
