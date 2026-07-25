"""ERA5-Land meteorological drivers — GEE + Open-Meteo archive (real reanalysis only)."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from data_ingestion.cache import save_parquet
from data_ingestion.data_provenance import is_local_data_mode, is_real_data_mode, prefer_local_files, require_real_source

logger = logging.getLogger(__name__)

OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def generate_synthetic_meteo(config: dict) -> pd.DataFrame:
    """Hourly meteo summary for study period (synthetic mode only)."""
    dates = pd.date_range(config["date_range"]["start"], config["date_range"]["end"], freq="D")
    rng = np.random.default_rng(99)
    rows = []
    for d in dates:
        for hour in range(0, 24, 3):
            base_t = 28 + 6 * np.sin((hour - 14) * np.pi / 12) + rng.normal(0, 0.5)
            rows.append(
                {
                    "datetime": pd.Timestamp(d) + pd.Timedelta(hours=hour),
                    "hour": hour,
                    "day": d.day,
                    "month": d.month,
                    "season": (d.month % 12 + 3) // 3,
                    "temp_2m_c": base_t,
                    "dewpoint_c": base_t - 8 + rng.normal(0, 0.3),
                    "humidity_proxy": 0.55 + rng.normal(0, 0.05),
                    "wind_ms": 2.5 + rng.normal(0, 0.5),
                    "solar_radiation_wm2": max(0, 800 * np.sin(hour * np.pi / 24)),
                    "heatwave_flag": int(base_t > 38),
                }
            )
    return pd.DataFrame(rows)


def _bbox_centroid(bbox: list[float]) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2


def _fetch_open_meteo_hourly(config: dict) -> pd.DataFrame:
    """Open-Meteo archive — ERA5 reanalysis (real historical meteo)."""
    lon, lat = _bbox_centroid(config["bbox"])
    timezone = config.get("timezone", "Asia/Kolkata")
    resp = requests.get(
        OPEN_METEO_ARCHIVE,
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": config["date_range"]["start"][:10],
            "end_date": config["date_range"]["end"][:10],
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "dewpoint_temperature_2m",
                    "windspeed_10m",
                    "shortwave_radiation",
                ]
            ),
            "timezone": timezone,
        },
        timeout=120,
    )
    resp.raise_for_status()
    payload = resp.json()
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        raise ValueError("Open-Meteo returned no hourly rows")

    rows = []
    for i, t in enumerate(times):
        temp = hourly["temperature_2m"][i]
        if temp is None:
            continue
        dew = hourly.get("dewpoint_temperature_2m", [None] * len(times))[i]
        wind = hourly.get("windspeed_10m", [None] * len(times))[i]
        solar = hourly.get("shortwave_radiation", [None] * len(times))[i]
        ts = pd.Timestamp(t)
        temp_f = float(temp)
        dew_f = float(dew) if dew is not None else temp_f - 8.0
        rh = max(0.2, min(0.95, 0.55 + (temp_f - dew_f) * -0.04))
        rows.append(
            {
                "datetime": ts,
                "hour": int(ts.hour),
                "day": int(ts.day),
                "month": int(ts.month),
                "season": (int(ts.month) % 12 + 3) // 3,
                "temp_2m_c": temp_f,
                "dewpoint_c": dew_f,
                "humidity_proxy": rh,
                "wind_ms": float(wind) if wind is not None else 2.5,
                "solar_radiation_wm2": float(solar) if solar is not None else 0.0,
                "heatwave_flag": int(temp_f > 38),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("Open-Meteo hourly table empty after parsing")
    logger.info("ERA5 meteo from Open-Meteo archive: %d hourly rows at (%.4f, %.4f)", len(df), lat, lon)
    return df


def _fetch_era5_gee_daily(config: dict) -> pd.DataFrame:
    """ERA5-Land daily means at city centroid via Google Earth Engine."""
    import ee

    from data_ingestion.gee_client import get_study_region, init_gee

    if not init_gee(config=config):
        raise RuntimeError("GEE not initialized")
    region = get_study_region(config["bbox"])
    centroid = region.centroid(maxError=1)
    coll = (
        ee.ImageCollection(config["era5_land"]["collection"])
        .filterBounds(region)
        .filterDate(config["date_range"]["start"], config["date_range"]["end"])
        .select(
            [
                "temperature_2m",
                "dewpoint_temperature_2m",
                "u_component_of_wind_10m",
                "v_component_of_wind_10m",
                "surface_solar_radiation_downwards",
            ]
        )
    )

    def _daily_mean(img: ee.Image) -> ee.Feature:
        stats = img.reduceRegion(ee.Reducer.mean(), centroid, scale=11132, maxPixels=1e9)
        return ee.Feature(
            None,
            {
                "datetime": img.date().format("YYYY-MM-dd"),
                "temp_k": stats.get("temperature_2m"),
                "dew_k": stats.get("dewpoint_temperature_2m"),
                "u_wind": stats.get("u_component_of_wind_10m"),
                "v_wind": stats.get("v_component_of_wind_10m"),
                "solar_j": stats.get("surface_solar_radiation_downwards"),
            },
        )

    fc = coll.map(_daily_mean)
    features = fc.getInfo().get("features", [])
    if not features:
        raise ValueError("GEE ERA5 returned no daily features")

    rows = []
    for feat in features:
        props = feat.get("properties", {})
        if props.get("temp_k") is None:
            continue
        temp_c = float(props["temp_k"]) - 273.15
        dew_c = float(props["dew_k"]) - 273.15 if props.get("dew_k") is not None else temp_c - 8
        u = float(props.get("u_wind") or 0)
        v = float(props.get("v_wind") or 0)
        solar = float(props.get("solar_j") or 0) / 3600.0
        ts = pd.Timestamp(props["datetime"])
        rows.append(
            {
                "datetime": ts + pd.Timedelta(hours=12),
                "hour": 12,
                "day": ts.day,
                "month": ts.month,
                "season": (ts.month % 12 + 3) // 3,
                "temp_2m_c": temp_c,
                "dewpoint_c": dew_c,
                "humidity_proxy": max(0.2, min(0.95, 0.55 + (temp_c - dew_c) * -0.04)),
                "wind_ms": float(np.hypot(u, v)),
                "solar_radiation_wm2": solar,
                "heatwave_flag": int(temp_c > 38),
            }
        )
    df = pd.DataFrame(rows)
    logger.info("ERA5 meteo from GEE: %d daily rows", len(df))
    return df


def fetch_real_meteo(config: dict) -> pd.DataFrame:
    """Fetch real ERA5-based meteorology (GEE first, then Open-Meteo archive)."""
    errors: list[str] = []
    try:
        return _fetch_era5_gee_daily(config)
    except Exception as exc:
        errors.append(f"GEE: {exc}")
        logger.warning("GEE ERA5 fetch failed (%s) — trying Open-Meteo archive.", exc)
    try:
        return _fetch_open_meteo_hourly(config)
    except Exception as exc:
        errors.append(f"Open-Meteo: {exc}")
        raise RuntimeError("Real meteo fetch failed — " + "; ".join(errors)) from exc


def ingest_era5_land(config: dict, out_dir: Path) -> Path:
    out_path = out_dir / "tables" / "era5_land_hourly.parquet"
    if out_path.exists() and not config.get("force_refresh"):
        return out_path

    # D-03 local UTCI NetCDF (Copernicus CDS download)
    if is_local_data_mode(config) or prefer_local_files(config):
        try:
            from data_ingestion.era5_utci_local import ingest_era5_utci_local

            return ingest_era5_utci_local(config, out_dir)
        except FileNotFoundError as exc:
            if is_local_data_mode(config):
                raise
            logger.warning("Local UTCI not configured (%s) — using GEE/Open-Meteo.", exc)

    if is_real_data_mode(config):
        try:
            df = fetch_real_meteo(config)
        except Exception as exc:
            require_real_source(config, "ERA5-Land meteorology", exc)
            raise
    else:
        df = generate_synthetic_meteo(config)

    save_parquet(df, out_path)
    logger.info("Meteo table saved to %s (%s rows)", out_path, len(df))
    return out_path
