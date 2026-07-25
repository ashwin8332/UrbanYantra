"""FastAPI backend — serves precomputed pipeline outputs + live scenario scoring."""

from __future__ import annotations

import sys
from pathlib import Path

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services import city_data, heatmap, model_inference, thermal_overlay
from backend.app.services.llm_chat import llm_chat_response
from backend.app.services.report_generator import generate_report

app = FastAPI(
    title="UrbanYantra API",
    description="Urban Heat Mitigation — physics-informed AI intelligence platform",
    version="1.0.0",
)

_cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_extra = os.environ.get("CORS_ALLOW_ORIGINS", "")
if _extra:
    _cors_origins.extend(o.strip() for o in _extra.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://.*\.(vercel\.app|hf\.space)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScenarioRequest(BaseModel):
    city_key: str = "Bengaluru"
    cool_roofs_pct: float = Field(0, ge=0, le=100)
    green_roofs_pct: float = Field(0, ge=0, le=100)
    urban_greening_pct: float = Field(0, ge=0, le=100)
    blue_infra_pct: float = Field(0, ge=0, le=100)
    budget_m_usd: float = Field(5.0, ge=0, le=50)


class ChatRequest(BaseModel):
    city_key: str = "Bengaluru"
    message: str
    history: list[dict] = []


class PredictRequest(BaseModel):
    city_key: str = "Bengaluru"
    lon: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)


@app.get("/")
def root():
    return {"service": "UrbanYantra API", "docs": "/docs"}


@app.get("/cities")
def list_cities():
    return city_data.list_cities()


@app.get("/cities/{city_key}/summary")
def city_summary(city_key: str):
    try:
        return city_data.get_city_summary(city_key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/cities/{city_key}/calibration")
def city_calibration(city_key: str):
    try:
        return city_data.get_station_calibration(city_key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/cities/{city_key}/domains")
def city_domains(city_key: str):
    """Named planning wards for simulator target domain (e.g. Borivali, Colaba)."""
    try:
        return city_data.build_ward_geojson(city_key, rows=5, cols=4)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/cities/{city_key}/wards")
def city_wards(
    city_key: str,
    step: int | None = Query(2, ge=1, le=20),
    mask_water: bool = Query(True),
):
    try:
        return heatmap.build_fine_grid_geojson(city_key, step=step, mask_water=mask_water)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/heatmap/{layer}.png")
def heatmap_png(city_key: str, layer: str):
    try:
        png = heatmap.get_heatmap_png(city_key, layer)
        return Response(content=png, media_type="image/png")
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/heatmap/{layer}/meta")
def heatmap_meta(city_key: str, layer: str):
    try:
        return heatmap.get_heatmap_meta(city_key, layer)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/thermal/overlay/meta")
def city_thermal_overlay_meta(city_key: str):
    """Georeferenced Landsat thermal overlay metadata (corner coordinates, Kelvin scale)."""
    try:
        return thermal_overlay.get_thermal_overlay_meta(city_key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/thermal/overlay.png")
def city_thermal_overlay_png(city_key: str):
    """RGBA thermal satellite overlay PNG aligned to Landsat georef."""
    try:
        png = thermal_overlay.get_thermal_overlay_png(city_key)
        return Response(content=png, media_type="image/png")
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/thermal/tiles")
def city_thermal_tiles(city_key: str):
    """Deprecated — use /thermal/overlay/meta. Kept for backwards compatibility."""
    try:
        meta = thermal_overlay.get_thermal_overlay_meta(city_key)
        b = meta["bounds"]
        return {
            "city_key": city_key,
            "tile_url": "",
            "vmin_k": meta["vmin_k"],
            "vmax_k": meta["vmax_k"],
            "unit": "K",
            "source": meta["source"],
            "bounds": b,
            "overlay_url": f"/cities/{city_key}/thermal/overlay.png",
            "coordinates": meta["coordinates"],
        }
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/sample-points")
def sample_points(city_key: str, stride: int = Query(2, ge=1, le=12)):
    try:
        return heatmap.build_sample_points_geojson(city_key, stride=stride)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/hotspots")
def city_hotspots(city_key: str):
    try:
        return city_data.get_hotspots(city_key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/drivers")
def city_drivers(city_key: str):
    try:
        return city_data.get_drivers(city_key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/data-audit")
def city_data_audit(city_key: str):
    try:
        return city_data.get_data_audit(city_key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/benchmarks")
def city_benchmarks(city_key: str):
    try:
        return city_data.get_benchmark_summary(city_key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/usp")
def city_usp(city_key: str):
    try:
        return city_data.get_usp_metrics(city_key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/cooling-potential")
def cooling_potential(city_key: str):
    try:
        return city_data.get_cooling_potential(city_key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/climate")
def climate_projection(city_key: str):
    try:
        return city_data.get_climate_projection(city_key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/report")
def city_report(city_key: str):
    """Generate and return a comprehensive PDF report for the city."""
    try:
        pdf_bytes = generate_report(city_key)
        filename = f"UrbanYantra_{city_key}_report.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Report generation failed: {e}") from e


@app.get("/cities/{city_key}/model-metrics")
def model_metrics(city_key: str):
    try:
        return model_inference.get_model_metrics(city_key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/predictions/grid")
def predictions_grid(city_key: str, stride: int = Query(4, ge=1, le=20)):
    try:
        return model_inference.build_predictions_grid_geojson(city_key, stride=stride)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.post("/predict/lst")
def predict_lst(body: PredictRequest):
    try:
        return model_inference.predict_lst(body.city_key, body.lon, body.lat)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.post("/predict/hotspot")
def predict_hotspot(body: PredictRequest):
    try:
        return model_inference.predict_hotspot(body.city_key, body.lon, body.lat)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.post("/predict/point")
def predict_point(body: PredictRequest):
    try:
        return model_inference.predict_point(body.city_key, body.lon, body.lat)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/ranking/{city_key}")
def ranking(city_key: str, limit: int = 30):
    try:
        return city_data.get_ranking(city_key, limit=limit)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/cities/{city_key}/interventions")
def interventions(city_key: str, limit: int = 30):
    """Return ranked cooling intervention zones (pixel-level rankings CSV/JSON)."""
    try:
        return city_data.get_ranking(city_key, limit=limit)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.post("/scenario")
def scenario(body: ScenarioRequest):
    try:
        return city_data.run_scenario(
            body.city_key,
            body.cool_roofs_pct,
            body.green_roofs_pct,
            body.urban_greening_pct,
            body.blue_infra_pct,
            body.budget_m_usd,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.post("/scenario/compare")
def scenario_compare(body: ScenarioRequest):
    try:
        return city_data.run_scenario_comparison(
            body.city_key,
            body.cool_roofs_pct,
            body.green_roofs_pct,
            body.urban_greening_pct,
            body.blue_infra_pct,
            body.budget_m_usd,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.post("/chat")
def chat(body: ChatRequest):
    try:
        reply = llm_chat_response(
            message=body.message,
            city_key=body.city_key,
            conversation_history=body.history or [],
        )
        return {"reply": reply}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e
