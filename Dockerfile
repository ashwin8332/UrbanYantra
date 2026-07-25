# UrbanYantra FastAPI — Hugging Face Space (Docker SDK, port 7860)
# Build: docker build -t urbanyantra-api .
# HF Space: connect this GitHub repo; HF uses this Dockerfile automatically.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

# Default outputs dataset (override via Space secret HF_OUTPUTS_REPO if needed)
ENV HF_OUTPUTS_REPO=sleepingbeauty11/UrbanYantra-outputs

COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY backend/ backend/
COPY configs/ configs/
COPY geography/ geography/
COPY features/ features/
COPY simulation/ simulation/
COPY data/benchmarks/ data/benchmarks/
COPY scripts/sync_outputs_from_hf.py scripts/sync_outputs_from_hf.py
COPY scripts/upload_outputs_to_hf.py scripts/upload_outputs_to_hf.py
COPY utils.py utils.py

RUN python -c "from backend.app.main import app; print('import ok')"

EXPOSE 7860
# Use sh -c (not entrypoint.sh) — avoids Windows CRLF breaking bash shebang on Linux
CMD ["sh", "-c", "python /app/scripts/sync_outputs_from_hf.py && exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
