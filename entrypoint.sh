#!/bin/bash
set -euo pipefail

echo "UrbanYantra API — syncing outputs from Hugging Face..."
python /app/scripts/sync_outputs_from_hf.py

echo "Starting FastAPI on port ${PORT:-7860}..."
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-7860}"
