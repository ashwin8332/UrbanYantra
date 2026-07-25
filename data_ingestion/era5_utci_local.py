"""D-03 — Local ERA5 / ECMWF UTCI NetCDF files (Copernicus CDS download)."""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from data_ingestion.cache import save_parquet

logger = logging.getLogger(__name__)

_UTCI_VAR_CANDIDATES = ("utci", "UTCI", "utci_calc", "unknown")


def _extract_utci_zip(zip_path: Path, dest: Path, start: pd.Timestamp, end: pd.Timestamp) -> Path | None:
    """Extract UTCI NetCDF files from a cached Copernicus/Drive zip once."""
    dest.mkdir(parents=True, exist_ok=True)
    existing = list(dest.rglob("ECMWF_utci_*.nc")) + list(dest.rglob("*.nc"))
    if existing:
        return existing[0].parent
    if not zip_path.exists() or not zipfile.is_zipfile(zip_path):
        return None
    logger.info("Extracting UTCI NetCDF files from %s â†’ %s", zip_path.name, dest)
    with zipfile.ZipFile(zip_path) as zf:
        members = []
        for member in zf.namelist():
            if not member.lower().endswith(".nc"):
                continue
            ts = _parse_nc_date(Path(member))
            if ts is not None and start <= ts <= end:
                members.append(member)
        if not members:
            return None
        for member in members:
            zf.extract(member, dest)
    extracted = list(dest.rglob("ECMWF_utci_*.nc")) + list(dest.rglob("*.nc"))
    return extracted[0].parent if extracted else None


def _local_utci_dir(config: dict) -> Path | None:
    from data_ingestion.remote_cache import ensure_urban_dataset_cached

    # 1) After Hugging Face sync — find .nc anywhere under urban_dataset cache
    remote = config.get("remote_data") or {}
    if remote.get("urban_dataset_folder"):
        try:
            start = pd.Timestamp(config["date_range"]["start"])
            end = pd.Timestamp(config["date_range"]["end"])
            root = ensure_urban_dataset_cached(config)
            nc_files = [
                p
                for p in list(root.rglob("ECMWF_utci_*.nc")) + list(root.rglob("*.nc"))
                if (ts := _parse_nc_date(p)) is not None and start <= ts <= end
            ]
            if nc_files:
                # Use directory containing the NetCDF files
                return nc_files[0].parent
            zip_files = [
                p
                for p in root.rglob("*.zip")
                if "era5" in str(p).lower() or "utci" in str(p).lower() or "ecmwf" in str(p).lower()
            ]
            if zip_files:
                from data_ingestion.remote_cache import _cache_root

                extracted = _extract_utci_zip(zip_files[0], _cache_root(config) / "era5_utci", start, end)
                if extracted:
                    return extracted
        except Exception as exc:
            logger.warning("UTCI from Hugging Face cache failed: %s", exc)

    from data_ingestion.remote_cache import resolve_dataset_dir

    path = resolve_dataset_dir(config, "era5_utci_dir")
    if path and path.is_dir():
        return path
    raw = (config.get("local_data") or {}).get("era5_utci_dir", "")
    if raw:
        p = Path(str(raw)).expanduser()
        return p if p.is_dir() else None
    return None


def _parse_nc_date(path: Path) -> pd.Timestamp | None:
    match = re.search(r"(\d{8})", path.stem)
    if not match:
        return None
    return pd.Timestamp(match.group(1))


def _find_utci_var(ds: xr.Dataset) -> str:
    for name in _UTCI_VAR_CANDIDATES:
        if name in ds.data_vars:
            return name
    for name in ds.data_vars:
        if "utci" in name.lower():
            return name
    if len(ds.data_vars) == 1:
        return list(ds.data_vars)[0]
    raise KeyError(f"No UTCI variable in {list(ds.data_vars)}")


def _lat_lon_names(ds: xr.Dataset) -> tuple[str, str]:
    for lat, lon in [("latitude", "longitude"), ("lat", "lon"), ("y", "x")]:
        if lat in ds.coords and lon in ds.coords:
            return lat, lon
    raise KeyError(f"Cannot find lat/lon coords in {list(ds.coords)}")


def _bbox_mean_utci(ds: xr.Dataset, var: str, bbox: list[float]) -> float:
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_name, lon_name = _lat_lon_names(ds)
    lat_vals = ds[lat_name].values
    lon_vals = ds[lon_name].values
    lat_step = float(np.nanmedian(np.abs(np.diff(lat_vals)))) if len(lat_vals) > 1 else 0.25
    lon_step = float(np.nanmedian(np.abs(np.diff(lon_vals)))) if len(lon_vals) > 1 else 0.25
    if (max_lat - min_lat) < lat_step:
        pad = (lat_step - (max_lat - min_lat)) / 2 + 1e-6
        min_lat -= pad
        max_lat += pad
    if (max_lon - min_lon) < lon_step:
        pad = (lon_step - (max_lon - min_lon)) / 2 + 1e-6
        min_lon -= pad
        max_lon += pad
    lat_slice = slice(min_lat, max_lat) if lat_vals[0] < lat_vals[-1] else slice(max_lat, min_lat)
    sub = ds[var].sel(**{lat_name: lat_slice, lon_name: slice(min_lon, max_lon)})
    arr = sub.values.astype(np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        center_lat = (bbox[1] + bbox[3]) / 2
        center_lon = (bbox[0] + bbox[2]) / 2
        sub = ds[var].sel(**{lat_name: center_lat, lon_name: center_lon}, method="nearest")
        arr = sub.values.astype(np.float64)
        arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        raise ValueError("UTCI subset empty for bbox")
    value = float(np.nanmean(arr))
    if value > 100:
        value -= 273.15
    return value


def load_utci_timeseries(config: dict) -> pd.DataFrame:
    """Build daily UTCI + derived meteo columns from local NetCDF folder."""
    utci_dir = _local_utci_dir(config)
    if utci_dir is None:
        raise FileNotFoundError(
            "Set local_data.era5_utci_dir in configs/local_datasets.yaml to your extracted ECMWF_utci_*.nc folder"
        )

    start = pd.Timestamp(config["date_range"]["start"])
    end = pd.Timestamp(config["date_range"]["end"])
    rows: list[dict] = []

    for nc_path in sorted(utci_dir.glob("*.nc")):
        ts = _parse_nc_date(nc_path)
        if ts is None or ts < start or ts > end:
            continue
        with xr.open_dataset(nc_path) as ds:
            var = _find_utci_var(ds)
            utci_c = _bbox_mean_utci(ds, var, config["bbox"])
        # UTCI ≈ human thermal stress; derive humidity proxy for feature table compatibility
        rows.append(
            {
                "datetime": ts + pd.Timedelta(hours=15),
                "hour": 15,
                "day": int(ts.day),
                "month": int(ts.month),
                "season": (int(ts.month) % 12 + 3) // 3,
                "utci_c": utci_c,
                "temp_2m_c": utci_c * 0.85,
                "dewpoint_c": utci_c - 10.0,
                "humidity_proxy": max(0.2, min(0.95, 0.45 + (utci_c - 30) * 0.02)),
                "wind_ms": 2.5,
                "solar_radiation_wm2": 600.0,
                "heatwave_flag": int(utci_c >= 38),
                "source": "era5_utci_local_nc",
            }
        )

    if not rows:
        raise ValueError(f"No UTCI NetCDF files in range {start.date()}–{end.date()} under {utci_dir}")

    df = pd.DataFrame(rows).sort_values("datetime")
    logger.info("Loaded %d UTCI daily files from %s", len(df), utci_dir)
    return df


def ingest_era5_utci_local(config: dict, out_dir: Path) -> Path:
    """Write era5_land_hourly.parquet from local UTCI NetCDF (D-03)."""
    out_path = out_dir / "tables" / "era5_land_hourly.parquet"
    utci_raster = out_dir / "rasters" / "utci_era5.tif"

    df = load_utci_timeseries(config)
    save_parquet(df, out_path)

    # Export mean UTCI raster placeholder (constant field — spatial UTCI grid needs full mosaic)
    from data_ingestion.cache import save_geotiff
    from utils import grid_shape_from_bbox

    h, w = grid_shape_from_bbox(config["bbox"], config.get("target_resolution_m", 10), max_side=120)
    mean_utci = float(df["utci_c"].mean())
    save_geotiff(np.full((h, w), mean_utci, dtype=np.float32), utci_raster, config["bbox"])

    logger.info("ERA5 UTCI local ingest → %s (%d rows, mean UTCI %.1f°C)", out_path, len(df), mean_utci)
    return out_path
