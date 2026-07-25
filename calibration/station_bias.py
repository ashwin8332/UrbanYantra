"""CPCB/IMD station bias calibration — Landsat LST vs ground air temperature."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def _summer_daily_mean_air_c(
    lat: float,
    lon: float,
    start: str,
    end: str,
    months: list[int],
    timezone: str = "Asia/Kolkata",
) -> float | None:
    """Open-Meteo historical 2 m air temperature (IMD/CPCB proxy when live API unavailable)."""
    try:
        resp = requests.get(
            OPEN_METEO_ARCHIVE,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": start[:10],
                "end_date": end[:10],
                "daily": "temperature_2m_mean",
                "timezone": timezone,
            },
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        times = payload.get("daily", {}).get("time", [])
        temps = payload.get("daily", {}).get("temperature_2m_mean", [])
        if not times or not temps:
            return None
        summer_vals = []
        for t, v in zip(times, temps):
            if v is None:
                continue
            month = int(t[5:7])
            if month in months:
                summer_vals.append(float(v))
        return float(np.mean(summer_vals)) if summer_vals else None
    except Exception as exc:
        logger.warning("Open-Meteo fetch failed (%.4f, %.4f): %s", lat, lon, exc)
        return None


def _gee_era5_summer_air_c(
    lat: float,
    lon: float,
    start: str,
    end: str,
    months: list[int],
    config: dict,
) -> float | None:
    """ERA5-Land 2 m temperature at station via GEE (when authenticated)."""
    try:
        import ee

        from data_ingestion.gee_client import init_gee

        if not init_gee(config=config):
            return None
        point = ee.Geometry.Point([lon, lat])
        coll = (
            ee.ImageCollection(config["era5_land"]["collection"])
            .filterBounds(point)
            .filterDate(start, end)
        )
        month_filters = [ee.Filter.calendarRange(int(m), int(m), "month") for m in months]
        coll = coll.filter(ee.Filter.Or(month_filters))
        mean_k = coll.select("temperature_2m").mean()
        val_k = mean_k.reduceRegion(ee.Reducer.mean(), point, scale=11132).get("temperature_2m")
        if val_k is None:
            return None
        return float(val_k.getInfo()) - 273.15
    except Exception as exc:
        logger.debug("GEE ERA5 station sample failed: %s", exc)
        return None


from features.display_pixels import visible_pixels


def _sample_lst_at_station(df: pd.DataFrame, lon: float, lat: float) -> float | None:
    land = visible_pixels(df)
    if land.empty:
        land = df
    dist = (land["lon"] - lon) ** 2 + (land["lat"] - lat) ** 2
    row = land.loc[dist.idxmin()]
    return float(row["lst_c"])


def run_station_calibration(config: dict, df: pd.DataFrame, out_dir: Path) -> dict[str, Any]:
    """
    Compute city-wide LST bias offset from CPCB reference stations.

    lst_calibrated = lst_satellite + bias_c
    bias_c = mean(air_temp_station - lst_satellite_at_station)
    """
    cal_dir = out_dir / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    out_json = cal_dir / "station_calibration.json"

    if out_json.exists() and not config.get("force_refresh"):
        return json.loads(out_json.read_text(encoding="utf-8"))

    stations = config.get("stations", [])
    if not stations:
        result = {
            "bias_c": 0.0,
            "method": "none",
            "stations": [],
            "note": "No stations in config",
        }
        out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    dr = config.get("date_range", {})
    start, end = dr.get("start", "2020-01-01"), dr.get("end", "2024-12-31")
    months = dr.get("lst_months", [3, 4, 5, 6])
    tz = config.get("timezone", "Asia/Kolkata")
    use_gee = config.get("data_mode") == "gee"

    records = []
    for st in stations:
        lon, lat = float(st["lon"]), float(st["lat"])
        lst_sat = _sample_lst_at_station(df, lon, lat)
        if lst_sat is None:
            continue

        air_c = None
        air_source = "open_meteo"
        if use_gee:
            air_c = _gee_era5_summer_air_c(lat, lon, start, end, months, config)
            if air_c is not None:
                air_source = "era5_land_gee"
        if air_c is None:
            air_c = _summer_daily_mean_air_c(lat, lon, start, end, months, tz)
            air_source = "open_meteo_archive"

        if air_c is None:
            continue

        delta = air_c - lst_sat
        records.append(
            {
                "name": st.get("name", "station"),
                "lon": lon,
                "lat": lat,
                "agency": "CPCB",
                "air_temp_c": round(air_c, 2),
                "lst_satellite_c": round(lst_sat, 2),
                "delta_air_minus_lst_c": round(delta, 2),
                "air_source": air_source,
            }
        )

    if not records:
        result = {
            "bias_c": 0.0,
            "method": "fallback_zero",
            "stations": [],
            "note": "Could not fetch air temperature for stations",
        }
    else:
        bias = float(np.mean([r["delta_air_minus_lst_c"] for r in records]))
        result = {
            "bias_c": round(bias, 3),
            "method": "cpcb_stations_air_minus_lst_mean",
            "date_range": {"start": start, "end": end, "lst_months": months},
            "stations": records,
            "note": "LST_calibrated = LST_satellite + bias_c (aligns LST toward summer 2 m air reference)",
        }

    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("Station calibration bias=%.2f°C (%d stations)", result["bias_c"], len(records))
    return result


def apply_calibration(df: pd.DataFrame, calibration: dict[str, Any]) -> pd.DataFrame:
    bias = float(calibration.get("bias_c", 0.0))
    out = df.copy()
    out["lst_calibrated_c"] = (out["lst_c"] + bias).astype(np.float32)
    return out


def load_calibration(out_dir: Path) -> dict[str, Any]:
    path = out_dir / "calibration" / "station_calibration.json"
    if not path.exists():
        return {"bias_c": 0.0, "stations": []}
    return json.loads(path.read_text(encoding="utf-8"))
