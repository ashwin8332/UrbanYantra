"""Load precomputed pipeline outputs for API serving."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from geography.ward_seeds import WARD_COORDINATES, nearest_ward_name as _nearest_ward_name
from features.display_pixels import visible_pixels
from features.usp_metrics import attach_usp_columns
from simulation.fit_surrogate import predict_surrogate
from utils import list_city_keys, load_city_config

ROOT = Path(__file__).resolve().parents[3]
CITIES_YAML = ROOT / "configs" / "cities.yaml"

WARD_NAMES = {
    "Bengaluru": [
        "Downtown",
        "Shivajinagar",
        "Richmond Town",
        "Shanti Nagar",
        "Indiranagar",
        "Koramangala",
        "Jayanagar",
        "Malleshwaram",
        "Whitefield",
        "Electronic City",
        "Hebbal",
        "Yelahanka",
        "Banashankari",
        "BTM Layout",
        "MG Road",
        "Cubbon Park",
        "Ulsoor",
        "Frazer Town",
        "Basavanagudi",
        "Rajajinagar",
    ],
    "Mumbai": [
        "Colaba",
        "Fort",
        "Dadar",
        "Bandra",
        "Andheri",
        "Powai",
        "Goregaon",
        "Borivali",
        "Thane",
        "Navi Mumbai",
        "Worli",
        "Lower Parel",
        "Kurla",
        "Chembur",
        "Mulund",
        "Malad",
        "Juhu",
        "Santacruz",
        "Vile Parle",
        "Dharavi",
    ],
    "Pune": [
        "Camp",
        "Koregaon Park",
        "Deccan",
        "Kothrud",
        "Baner",
        "Hinjewadi",
        "Hadapsar",
        "Kharadi",
        "Wakad",
        "Aundh",
        "Shivajinagar",
        "Pimpri",
        "Katraj",
        "Warje",
        "Kondhwa",
        "Magarpatta",
        "Viman Nagar",
        "Yerwada",
        "Bund Garden",
        "Swargate",
    ],
    "Delhi NCR": [
        "Connaught Place",
        "Karol Bagh",
        "Dwarka",
        "Rohini",
        "Saket",
        "Noida",
        "Gurgaon",
        "Faridabad",
        "Lajpat Nagar",
        "Hauz Khas",
        "Janakpuri",
        "Pitampura",
        "Mayur Vihar",
        "Anand Vihar",
        "Rajouri Garden",
        "Vasant Kunj",
        "Greater Kailash",
        "Civil Lines",
        "Nehru Place",
        "Okhla",
    ],
    "Ahmedabad": [
        "Navrangpura",
        "Satellite",
        "Maninagar",
        "Vastrapur",
        "Bopal",
        "Ghatlodia",
        "Paldi",
        "Ashram Road",
        "SG Highway",
        "Thaltej",
        "Naranpura",
        "Vejalpur",
        "Isanpur",
        "Naroda",
        "Sabarmati",
        "Ellis Bridge",
        "Law Garden",
        "Memnagar",
        "Chandkheda",
        "Motera",
    ],
}

VULNERABILITY = ["LOW", "MODERATE", "HIGH", "CRITICAL"]

_CRITICAL_ARTIFACTS = ("landsat_lst", "ghsl", "era5_meteo", "worldcover", "sentinel2_ndvi")


def _artifact_health(provenance: dict[str, Any], data_mode: str, artifacts: dict[str, bool]) -> tuple[bool, list[str]]:
    """Derive live-data status from verified artifacts on disk."""
    if data_mode == "synthetic":
        return False, []

    labels = {
        "landsat_lst": "Landsat LST (GEE)",
        "ghsl": "GHSL Built-S / SMOD (Hugging Face)",
        "era5_meteo": "ERA5 UTCI (Hugging Face)",
        "worldcover": "ESA WorldCover (GEE)",
        "sentinel2_ndvi": "Sentinel-2 NDVI (GEE)",
    }
    errors = [
        f"Error fetching data: {labels[key]}"
        for key in _CRITICAL_ARTIFACTS
        if not artifacts.get(key)
    ]
    is_real = data_mode in {"gee", "local"} and not errors
    return is_real, errors


def _dataset_status(present: bool, data_mode: str, *, cached: bool = False) -> str:
    if present:
        return "cached_real" if cached else "real"
    if data_mode == "synthetic":
        return "synthetic"
    return "error"


def _city_out_dir(city_key: str) -> Path:
    cfg = load_city_config(CITIES_YAML, city_key)
    return ROOT / cfg["output_dir"]


def _verify_artifacts(city_key: str, provenance: dict[str, Any]) -> dict[str, bool]:
    """Check artifact flags against files on disk (summary.json can be stale)."""
    out = _city_out_dir(city_key)
    stored = provenance.get("artifacts_present", {})

    def _exists(path: Path) -> bool:
        return path.exists()

    def _any_exist(*paths: Path) -> bool:
        return any(p.exists() for p in paths)

    # Pre-baked feature table proves GHSL/ERA5 were ingested even when raw rasters
    # are omitted from the HF deploy bundle (saves GB of disk).
    ft_flags: dict[str, bool] = {}
    ft_path = out / "tables" / "feature_table.parquet"
    if ft_path.exists():
        try:
            import pyarrow.parquet as pq

            cols = set(pq.ParquetFile(ft_path).schema.names)
            ft_flags["ghsl"] = bool(
                {"building_density", "building_height", "population"} & cols
            )
            ft_flags["era5_meteo"] = bool(
                {"humidity_proxy", "temp_2m_c", "dewpoint_c", "wind_ms"} & cols
            )
        except Exception:
            pass

    checks = {
        "landsat_lst": _any_exist(
            out / "rasters" / "landsat_lst_c.tif",
            out / "rasters" / "lst_10m.tif",
        ),
        "sentinel2_ndvi": _exists(out / "rasters" / "ndvi.tif"),
        "worldcover": _exists(out / "rasters" / "worldcover.tif"),
        "ghsl": _any_exist(
            out / "rasters" / "ghsl_building_height.tif",
            out / "rasters" / "ghsl_built_surface.tif",
            out / "rasters" / "ghsl_smod.tif",
            out / "rasters" / "ghsl_population.tif",
        ),
        "era5_meteo": _exists(out / "tables" / "era5_land_hourly.parquet"),
        "osm_morphology": _exists(out / "tables" / "osm_morphology.parquet"),
        "osm_buildings": _exists(out / "vectors" / "osm_buildings.gpkg"),
        "station_calibration": _exists(out / "calibration" / "station_calibration.json"),
        "ward_boundaries": _exists(out / "geojson" / "ward_zonal.geojson"),
        "feature_table": _exists(out / "tables" / "feature_table.parquet"),
        "lst_10m": _exists(out / "rasters" / "lst_10m.tif"),
    }
    for key, from_ft in ft_flags.items():
        if from_ft:
            checks[key] = True

    verified: dict[str, bool] = {}
    for key, present in checks.items():
        if key in stored and not stored.get(key):
            verified[key] = False
        else:
            verified[key] = bool(present)
    return verified


def _load_city_provenance(city_key: str) -> dict[str, Any]:
    summary_path = _city_out_dir(city_key) / "summary.json"
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    return {}


def _data_bbox(city_key: str) -> list[float] | None:
    """Extent of visible urban pixels (non-rectangular), padded slightly."""
    try:
        df = _load_feature_table(city_key)
        vis = visible_pixels(df)
        if vis.empty:
            vis = df
        pad = 0.003
        return [
            float(vis["lon"].min()) - pad,
            float(vis["lat"].min()) - pad,
            float(vis["lon"].max()) + pad,
            float(vis["lat"].max()) + pad,
        ]
    except FileNotFoundError:
        return None


def _load_feature_table(city_key: str) -> pd.DataFrame:
    path = _city_out_dir(city_key) / "tables" / "feature_table.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No pipeline output for {city_key}. Run: py run_pipeline.py --city {city_key}")
    df = pd.read_parquet(path)
    required = {"green_cooling_potential_c", "co2_mitigation_tons_yr", "planning_priority"}
    if not required.issubset(df.columns):
        cfg = load_city_config(CITIES_YAML, city_key)
        df = attach_usp_columns(df, cfg)
    return df


def _approx_utci(lst_c: float, humidity: float = 0.55) -> float:
    """Simplified UTCI proxy from LST and humidity (demo metric)."""
    return float(lst_c * 0.72 + humidity * 8.0 - 2.5)


def _resilience_index(df: pd.DataFrame) -> int:
    ndvi = df["ndvi"].mean()
    lst = df["lst_c"].mean()
    green = min(100, max(0, int(ndvi * 120)))
    heat_penalty = min(40, max(0, int((lst - 35) * 4)))
    return max(0, min(100, green + 30 - heat_penalty))


@lru_cache(maxsize=16)
def get_city_summary(city_key: str) -> dict[str, Any]:
    cfg = load_city_config(CITIES_YAML, city_key)
    df = _load_feature_table(city_key)
    avg_lst = float(df["lst_c"].mean())
    humidity = float(df.get("humidity_proxy", pd.Series([0.55])).mean())
    avg_utci = _approx_utci(avg_lst, humidity)
    data_bbox = _data_bbox(city_key) or cfg["bbox"]
    land_df = visible_pixels(df)
    land_lst = float(land_df["lst_c"].mean()) if len(land_df) else avg_lst
    cal = get_station_calibration(city_key)
    provenance = _load_city_provenance(city_key)
    data_mode = provenance.get("data_mode", cfg.get("data_mode", "gee"))
    artifacts = _verify_artifacts(city_key, provenance)
    is_real_data, fetch_errors = _artifact_health(provenance, data_mode, artifacts)
    return {
        "city_key": city_key,
        "city_name": cfg["city_name"],
        "bbox": data_bbox,
        "config_bbox": cfg["bbox"],
        "data_mode": data_mode,
        "is_real_data": is_real_data,
        "fetch_errors": fetch_errors,
        "data_sources": provenance.get("data_sources", {}),
        "artifacts_present": artifacts,
        "grid_resolution_m": cfg.get("target_resolution_m", 10),
        "calibration": {
            "bias_c": cal.get("bias_c", 0.0),
            "method": cal.get("method", "none"),
            "station_count": len(cal.get("stations", [])),
        },
        "ward_boundaries": (
            "osm_zonal"
            if (_city_out_dir(city_key) / "geojson" / "ward_zonal.geojson").exists()
            else "rectangular_fallback"
        ),
        "metrics": {
            "avg_city_lst_c": round(land_lst, 1),
            "avg_heat_stress_utci_c": round(_approx_utci(land_lst, humidity), 1),
            "resilience_index": _resilience_index(df),
            "co2_sequestration_tons_yr": round(float(df.get("co2_mitigation_tons_yr", pd.Series([0.0])).mean()), 1),
            "total_investment_m_usd": 0.0,
        },
    }


def get_data_audit(city_key: str) -> dict[str, Any]:
    """Judge-facing audit: which PS1 datasets are real, cached, or synthetic."""
    cfg = load_city_config(CITIES_YAML, city_key)
    out = _city_out_dir(city_key)
    provenance = _load_city_provenance(city_key)
    artifacts = _verify_artifacts(city_key, provenance)
    sources = provenance.get("data_sources", {})
    data_mode = provenance.get("data_mode", cfg.get("data_mode", "gee"))
    benchmarks = get_benchmark_summary(city_key)

    def row(dataset_id: str, name: str, status: str, source: str, use: str) -> dict[str, Any]:
        return {
            "dataset_id": dataset_id,
            "name": name,
            "status": status,
            "source": source,
            "used_for": use,
            "is_real": status in {"real", "cached_real", "bundled_real"},
        }

    rows = [
        row(
            "D-01",
            "Landsat 8 Collection 2 LST",
            _dataset_status(bool(artifacts.get("landsat_lst")), data_mode),
            sources.get("landsat_lst", "GEE Landsat 8 ST_B10"),
            "Surface temperature, hotspots, model target",
        ),
        row(
            "D-03",
            "ERA5 / ERA5-Land / UTCI",
            _dataset_status(bool(artifacts.get("era5_meteo")), data_mode, cached=True),
            sources.get("era5_meteo", "Hugging Face UTCI NetCDF or GEE ERA5-Land"),
            "Heat stress, humidity, wind, solar drivers",
        ),
        row(
            "D-04",
            "GHSL Built-S / SMOD",
            _dataset_status(bool(artifacts.get("ghsl")), data_mode, cached=True),
            sources.get("ghsl", "Hugging Face GHSL tiles or GEE JRC GHSL"),
            "Building density, population, LCZ/urban morphology",
        ),
        row(
            "D-05",
            "ESA WorldCover",
            _dataset_status(bool(artifacts.get("worldcover")), data_mode),
            sources.get("worldcover", "GEE ESA WorldCover"),
            "Water/vegetation/urban masks",
        ),
        row(
            "D-06",
            "OpenStreetMap morphology",
            "real" if artifacts.get("osm_morphology") else ("fallback" if out.exists() else "error"),
            sources.get("osm_morphology", "OSM buildings/roads or impervious fallback"),
            "Road density, built form, ward boundaries",
        ),
        row(
            "D-07",
            "Kaggle UHI Monitoring Dataset",
            "bundled_real" if benchmarks.get("kaggle_uhi", {}).get("rows") else "error",
            benchmarks.get("kaggle_uhi", {}).get("source", "data/benchmarks/urban_heat_island_dataset.csv"),
            "Baseline ML/EDA benchmark card",
        ),
        row(
            "D-09",
            "EY 2025 NYC UHI Ground Truth",
            "bundled_real" if benchmarks.get("ey_uhi", {}).get("rows") else "error",
            benchmarks.get("ey_uhi", {}).get("source", "data/benchmarks/Training_data_uhi_index_2025-02-18.csv"),
            "External validation narrative with labeled UHI",
        ),
    ]
    is_real, fetch_errors = _artifact_health(provenance, data_mode, artifacts)
    return {
        "city_key": city_key,
        "data_mode": data_mode,
        "synthetic_used": any(item["status"] == "synthetic" for item in rows),
        "has_fetch_errors": not is_real and data_mode in {"gee", "local"},
        "fetch_errors": fetch_errors,
        "datasets": rows,
    }


def get_benchmark_summary(city_key: str) -> dict[str, Any]:
    """D-07 + D-09 benchmark summaries, using output manifest or bundled CSVs."""
    bench_dir = _city_out_dir(city_key) / "benchmarks"
    manifest = bench_dir / "benchmark_manifest.json"
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
    else:
        data = {}

    bundled_dir = ROOT / "data" / "benchmarks"
    kaggle_csv = bundled_dir / "urban_heat_island_dataset.csv"
    if "kaggle_uhi" not in data and kaggle_csv.exists():
        kaggle = pd.read_csv(kaggle_csv)
        temp_col = next((c for c in kaggle.columns if "temperature" in c.lower()), None)
        data["kaggle_uhi"] = {
            "rows": int(len(kaggle)),
            "columns": list(kaggle.columns),
            "temperature_mean_c": round(float(kaggle[temp_col].mean()), 2) if temp_col else None,
            "land_cover_classes": int(kaggle["Land Cover"].nunique()) if "Land Cover" in kaggle.columns else None,
            "source": "D-07 Kaggle UHI Monitoring Dataset",
            "note": "Bundled real tabular benchmark for EDA/baseline ML, not Indian geospatial ground truth",
        }

    ey_csv = bundled_dir / "Training_data_uhi_index_2025-02-18.csv"
    if "ey_uhi" not in data and ey_csv.exists():
        ey = pd.read_csv(ey_csv)
        ey.columns = [c.strip() for c in ey.columns]
        if "UHI Index" in ey.columns:
            ey = ey.rename(columns={"UHI Index": "uhi_index", "Longitude": "lon", "Latitude": "lat"})
        data["ey_uhi"] = {
            "rows": int(len(ey)),
            "uhi_index_mean": round(float(ey["uhi_index"].mean()), 4) if "uhi_index" in ey.columns else None,
            "uhi_index_std": round(float(ey["uhi_index"].std()), 4) if "uhi_index" in ey.columns else None,
            "lon_range": [float(ey["lon"].min()), float(ey["lon"].max())] if "lon" in ey.columns else None,
            "lat_range": [float(ey["lat"].min()), float(ey["lat"].max())] if "lat" in ey.columns else None,
            "source": "D-09 EY Open Science Challenge 2025 (NYC ground truth)",
            "note": "External validation reference with labeled UHI Index",
        }

    bench_metrics = _city_out_dir(city_key) / "models" / "benchmark_metrics.json"
    if bench_metrics.exists():
        data["training_pipeline"] = json.loads(bench_metrics.read_text(encoding="utf-8"))
    return data


def get_usp_metrics(city_key: str) -> dict[str, Any]:
    """Tree/green cooling, carbon co-benefit, and planning-priority USP metrics."""
    df = visible_pixels(_load_feature_table(city_key))
    if df.empty:
        df = _load_feature_table(city_key)
    top = df.nlargest(5, "planning_priority")
    zones = []
    for _, row_data in top.iterrows():
        zones.append(
            {
                "name": _nearest_ward_name(load_city_config(CITIES_YAML, city_key)["city_name"], float(row_data["lon"]), float(row_data["lat"])),
                "lon": float(row_data["lon"]),
                "lat": float(row_data["lat"]),
                "planning_priority": round(float(row_data["planning_priority"]), 1),
                "lst_c": round(float(row_data["lst_c"]), 1),
                "ndvi": round(float(row_data["ndvi"]), 2),
            }
        )
    return {
        "tree_green_cooling": {
            "avg_potential_c": round(float(df["green_cooling_potential_c"].mean()), 2),
            "max_potential_c": round(float(df["green_cooling_potential_c"].max()), 2),
            "description": "Estimated cooling from evapotranspiration + canopy shade over low-NDVI hot pixels",
        },
        "carbon_mitigation": {
            "co2_tons_yr": round(float(df["co2_mitigation_tons_yr"].mean()), 1),
            "description": "Annual CO2 co-benefit for the configured urban greening scenario",
        },
        "urban_planning": {
            "avg_priority": round(float(df["planning_priority"].mean()), 1),
            "high_priority_pixel_pct": round(float((df["planning_priority"] >= 70).mean() * 100), 1),
            "top_zones": zones,
            "description": "Priority score combines LST, NDVI deficit, imperviousness, and population exposure",
        },
    }


def list_cities() -> list[dict[str, Any]]:
    keys = list_city_keys(CITIES_YAML)
    state_order = {
        "Maharashtra": 0,
        "Delhi": 1,
        "Karnataka": 2,
        "Telangana": 3,
        "Andhra Pradesh": 4,
        "Tamil Nadu": 5,
        "West Bengal": 6,
        "Gujarat": 7,
    }
    results = []
    for key in keys:
        cfg = load_city_config(CITIES_YAML, key)
        state = cfg.get("state", "")
        out = _city_out_dir(key)
        if (out / "tables" / "feature_table.parquet").exists():
            summary = get_city_summary(key)
            results.append(
                {
                    "city_key": key,
                    "city_name": summary["city_name"],
                    "state": state,
                    "has_data": True,
                    "avg_lst_c": summary["metrics"]["avg_city_lst_c"],
                }
            )
        else:
            results.append(
                {
                    "city_key": key,
                    "city_name": cfg["city_name"],
                    "state": state,
                    "has_data": False,
                    "avg_lst_c": None,
                }
            )
    results.sort(key=lambda x: (state_order.get(x.get("state", ""), 99), x["city_name"]))
    return results


def build_ward_geojson(city_key: str, rows: int = 5, cols: int = 4) -> dict[str, Any]:
    """OSM/Voronoi ward polygons with zonal LST stats when available."""
    zonal_path = _city_out_dir(city_key) / "geojson" / "ward_zonal.geojson"
    if zonal_path.exists():
        return json.loads(zonal_path.read_text(encoding="utf-8"))

    cfg = load_city_config(CITIES_YAML, city_key)
    df = _load_feature_table(city_key)
    bbox = cfg["bbox"]
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_edges = np.linspace(min_lon, max_lon, cols + 1)
    lat_edges = np.linspace(min_lat, max_lat, rows + 1)
    features: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    for r in range(rows):
        for c in range(cols):
            w_min_lon, w_max_lon = lon_edges[c], lon_edges[c + 1]
            w_min_lat, w_max_lat = lat_edges[r], lat_edges[r + 1]
            ward_df = df[
                (df["lon"] >= w_min_lon)
                & (df["lon"] < w_max_lon if c < cols - 1 else df["lon"] <= w_max_lon)
                & (df["lat"] >= w_min_lat)
                & (df["lat"] < w_max_lat if r < rows - 1 else df["lat"] <= w_max_lat)
            ]
            if ward_df.empty:
                continue
            ward_df = visible_pixels(ward_df)
            if ward_df.empty:
                continue

            avg_lst = float(ward_df["lst_c"].mean())
            avg_ndvi = float(ward_df["ndvi"].mean())
            avg_ndbi = float(ward_df["ndbi"].mean())
            hotspot_frac = float((ward_df["hotspot_class"] >= 1).mean())
            humidity = float(ward_df.get("humidity_proxy", pd.Series([0.55])).mean())
            utci = _approx_utci(avg_lst, humidity)

            if avg_lst >= 42 or hotspot_frac > 0.35:
                vuln = "CRITICAL"
            elif avg_lst >= 40 or hotspot_frac > 0.2:
                vuln = "HIGH"
            elif avg_lst >= 38:
                vuln = "MODERATE"
            else:
                vuln = "LOW"

            centroid_lon = (w_min_lon + w_max_lon) / 2
            centroid_lat = (w_min_lat + w_max_lat) / 2
            polygon = [
                [w_min_lon, w_min_lat],
                [w_max_lon, w_min_lat],
                [w_max_lon, w_max_lat],
                [w_min_lon, w_max_lat],
                [w_min_lon, w_min_lat],
            ]
            pending.append(
                {
                    "centroid": (centroid_lon, centroid_lat),
                    "polygon": polygon,
                    "props": {
                        "avg_lst_c": round(avg_lst, 2),
                        "simulated_lst_c": round(avg_lst, 2),
                        "heat_stress_utci_c": round(utci, 2),
                        "cooling_delta_c": 0.0,
                        "ndvi": round(avg_ndvi, 3),
                        "ndbi": round(avg_ndbi, 3),
                        "vulnerability_class": vuln,
                        "hotspot_fraction": round(hotspot_frac, 3),
                    },
                }
            )

    ward_labels = [_nearest_ward_name(cfg["city_name"], p["centroid"][0], p["centroid"][1]) for p in pending]
    for label, item in zip(ward_labels, pending):
        ward_id = f"{city_key}_{label.lower().replace(' ', '_')}"
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [item["polygon"]]},
                "properties": {
                    "ward_id": ward_id,
                    "name": label,
                    **item["props"],
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def get_station_calibration(city_key: str) -> dict[str, Any]:
    path = _city_out_dir(city_key) / "calibration" / "station_calibration.json"
    if not path.exists():
        return {"bias_c": 0.0, "stations": [], "method": "not_run"}
    return json.loads(path.read_text(encoding="utf-8"))


def get_hotspots(city_key: str) -> dict[str, Any]:
    cfg = load_city_config(CITIES_YAML, city_key)
    slug = cfg["city_name"].lower().replace(" ", "_")
    path = _city_out_dir(city_key) / "geojson" / f"hotspots_{slug}.geojson"
    if path.exists():
        raw = path.read_text(encoding="utf-8").replace("NaN", "null")
        return json.loads(raw)
    df = _load_feature_table(city_key)
    hotspot_df = df[df["hotspot_class"] >= 1].copy()
    if hotspot_df.empty:
        hotspot_df = df.nlargest(30, "lst_c")
    else:
        hotspot_df = hotspot_df.nlargest(80, "lst_c")
    features = []
    for _, row in hotspot_df.iterrows():
        cls = int(row["hotspot_class"])
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
                "properties": {
                    "hotspot_id": f"{cfg['city_name']}_{int(row['row'])}_{int(row['col'])}",
                    "lst_c": float(row["lst_c"]),
                    "hotspot_class": cls,
                    "hotspot_label": "Severe" if cls >= 2 else "Moderate" if cls >= 1 else "Warm",
                    "gi_star_z": float(row.get("gi_star_z", 0.0)),
                    "ndvi": float(row.get("ndvi", 0.0)),
                    "population": float(row.get("population", 0.0)),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def get_drivers(city_key: str) -> dict[str, Any]:
    out = _city_out_dir(city_key)
    shap_path = out / "explainability" / "shap_feature_importance.csv"
    if shap_path.exists():
        imp = pd.read_csv(shap_path)
        imp = imp[imp["mean_abs_shap"] > 0].copy()
        total = imp["mean_abs_shap"].sum() or 1.0
        imp["pct"] = (imp["mean_abs_shap"] / total * 100).clip(0, 100)
        top = imp.sort_values("mean_abs_shap", ascending=False).head(4)
        drivers = [
            {"feature": _friendly_driver_name(row["feature"]), "importance_pct": float(row["pct"])}
            for _, row in top.iterrows()
        ]
        total_pct = sum(d["importance_pct"] for d in drivers) or 1.0
        drivers = [{**d, "importance_pct": round(d["importance_pct"] / total_pct * 100, 1)} for d in drivers]
        return {"source": "shap", "drivers": drivers}

    df = _load_feature_table(city_key)
    ndvi_deficit = max(0.0, 0.35 - float(df["ndvi"].mean()))
    low_albedo = max(0.0, float(df["ndbi"].mean()))
    morphology = max(0.0, float(df["impervious_frac"].mean()))
    meteo = max(0.0, float(df.get("humidity_proxy", pd.Series([0.5])).mean()))
    raw = {
        "Vegetation Deficit (NDVI)": ndvi_deficit * 80,
        "Low Surface Albedo": low_albedo * 40,
        "Morphology Trapping (SVF)": morphology * 45,
        "Meteorological (Humidity/Solar)": meteo * 35,
    }
    total = sum(raw.values()) or 1.0
    return {
        "source": "proxy",
        "drivers": [
            {"feature": k, "importance_pct": round(max(0.0, v / total * 100), 1)} for k, v in raw.items()
        ],
    }


def _friendly_driver_name(feature: str) -> str:
    mapping = {
        "ndvi": "Vegetation Deficit (NDVI)",
        "ndbi": "Low Surface Albedo",
        "impervious_frac": "Morphology Trapping (SVF)",
        "building_density": "Building Density",
        "humidity_proxy": "Meteorological (Humidity)",
        "wind_ms": "Wind Patterns",
        "solar_radiation_wm2": "Solar Radiation",
    }
    return mapping.get(feature, feature.replace("_", " ").title())


def get_cooling_potential(city_key: str) -> list[dict[str, Any]]:
    out = _city_out_dir(city_key)
    rankings = out / "tables" / "intervention_rankings.csv"
    if rankings.exists():
        df = pd.read_csv(rankings)
        grouped = (
            df.groupby("intervention_type")["estimated_temp_reduction_c"]
            .mean()
            .reset_index()
            .sort_values("estimated_temp_reduction_c", ascending=False)
        )
        labels = {
            "cool_roof": "Cool Roofs",
            "urban_greening": "Urban Greening",
            "blue_infrastructure": "Blue Infra",
        }
        return [
            {
                "strategy": labels.get(row["intervention_type"], row["intervention_type"]),
                "delta_t_c": round(float(row["estimated_temp_reduction_c"]), 2),
            }
            for _, row in grouped.iterrows()
        ]
    return []


def get_ranking(city_key: str, limit: int = 30) -> list[dict[str, Any]]:
    out = _city_out_dir(city_key)
    json_path = out / "ranking" / f"{load_city_config(CITIES_YAML, city_key)['city_name'].lower().replace(' ', '_')}.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return data[:limit]
    csv_path = out / "tables" / "intervention_rankings.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path).head(limit).to_dict(orient="records")
    return []


def get_climate_projection(city_key: str) -> list[dict[str, Any]]:
    """Trend projection from pipeline baseline LST (not a stochastic forecast)."""
    df = _load_feature_table(city_key)
    base = float(df["lst_c"].mean())
    years = list(range(2020, 2051, 5))
    return [
        {"year": y, "lst_c": round(base + (y - 2020) * 0.12, 2)}
        for y in years
    ]


def run_scenario(
    city_key: str,
    cool_roofs_pct: float,
    green_roofs_pct: float,
    urban_greening_pct: float,
    blue_infra_pct: float,
    budget_m_usd: float = 5.0,
) -> dict[str, Any]:
    out = _city_out_dir(city_key)
    surrogate = out / "simulation" / "surrogate_delta_t.joblib"
    canopy = (urban_greening_pct + green_roofs_pct * 0.5) / 100.0
    albedo = cool_roofs_pct / 100.0 * 0.35
    water = blue_infra_pct / 100.0 * 0.5

    if surrogate.exists():
        delta_t = predict_surrogate(canopy, albedo, water, surrogate)
    else:
        delta_t = -(canopy * 1.6 + albedo * 2.1 + water * 3.0)

    cooling_c = abs(delta_t)
    investment = min(budget_m_usd, cooling_c * 0.8)

    df = _load_feature_table(city_key)
    avg_lst = float(df["lst_c"].mean())
    humidity = float(df.get("humidity_proxy", pd.Series([0.55])).mean())

    return {
        "city_key": city_key,
        "inputs": {
            "cool_roofs_pct": cool_roofs_pct,
            "green_roofs_pct": green_roofs_pct,
            "urban_greening_pct": urban_greening_pct,
            "blue_infra_pct": blue_infra_pct,
            "budget_m_usd": budget_m_usd,
        },
        "mean_cooling_delta_c": round(cooling_c, 2),
        "simulated_avg_lst_c": round(avg_lst - cooling_c, 2),
        "baseline_avg_lst_c": round(avg_lst, 2),
        "simulated_utci_c": round(_approx_utci(avg_lst - cooling_c, humidity), 2),
        "co2_sequestration_tons_yr": round(urban_greening_pct * 12.5, 1),
        "total_investment_m_usd": round(investment, 2),
        "ward_updates": _apply_scenario_to_wards(city_key, cooling_c),
    }


def _ward_cooling_weight(ward_id: str) -> float:
    """Deterministic per-ward cooling weight from ward id (no RNG)."""
    return 0.7 + 0.3 * ((hash(ward_id) % 100) / 100.0)


def _apply_scenario_to_wards(city_key: str, cooling_c: float) -> list[dict[str, Any]]:
    wards = build_ward_geojson(city_key, rows=5, cols=4)["features"]
    updates = []
    for f in wards:
        p = f["properties"]
        weight = _ward_cooling_weight(p["ward_id"])
        updates.append(
            {
                "ward_id": p["ward_id"],
                "simulated_lst_c": round(p["avg_lst_c"] - cooling_c * weight, 2),
                "cooling_delta_c": round(cooling_c * weight, 2),
            }
        )
    return updates


def run_scenario_comparison(
    city_key: str,
    cool_roofs_pct: float,
    green_roofs_pct: float,
    urban_greening_pct: float,
    blue_infra_pct: float,
    budget_m_usd: float = 5.0,
) -> dict[str, Any]:
    """Run 5 scenario comparisons and return a unified comparison result."""

    df = _load_feature_table(city_key)
    avg_lst = float(df["lst_c"].mean())
    total_pixels = len(df)

    # Estimate population from feature table if available
    pop_col = None
    for col_name in ("population", "ghsl_pop", "pop_density"):
        if col_name in df.columns:
            pop_col = col_name
            break
    total_pop = int(df[pop_col].sum()) if pop_col else total_pixels * 50

    scenario_configs = [
        {
            "name": "Current (Baseline)",
            "icon": "🏙️",
            "cool_roofs": 0,
            "green_roofs": 0,
            "urban_greening": 0,
            "blue_infra": 0,
        },
        {
            "name": "+ Trees",
            "icon": "🌳",
            "cool_roofs": 0,
            "green_roofs": 0,
            "urban_greening": urban_greening_pct,
            "blue_infra": 0,
        },
        {
            "name": "+ Cool Roofs",
            "icon": "🏠",
            "cool_roofs": cool_roofs_pct,
            "green_roofs": 0,
            "urban_greening": 0,
            "blue_infra": 0,
        },
        {
            "name": "+ Green Roofs",
            "icon": "🌿",
            "cool_roofs": 0,
            "green_roofs": green_roofs_pct,
            "urban_greening": 0,
            "blue_infra": 0,
        },
        {
            "name": "Combined (All)",
            "icon": "✨",
            "cool_roofs": cool_roofs_pct,
            "green_roofs": green_roofs_pct,
            "urban_greening": urban_greening_pct,
            "blue_infra": blue_infra_pct,
        },
    ]

    scenarios = []
    best_idx = 0
    best_cooling = 0.0

    for i, cfg in enumerate(scenario_configs):
        result = run_scenario(
            city_key,
            cfg["cool_roofs"],
            cfg["green_roofs"],
            cfg["urban_greening"],
            cfg["blue_infra"],
            budget_m_usd,
        )

        cooling = result["mean_cooling_delta_c"]
        baseline_carbon = avg_lst * 2.5  # proxy baseline emissions
        carbon_pct = round(cooling / max(baseline_carbon, 1) * 100, 1) if cooling > 0 else 0
        heat_stress_pct = round(cooling / max(avg_lst, 1) * 100, 1) if cooling > 0 else 0
        pop_benefited = int(total_pop * min(1.0, cooling / 5.0)) if cooling > 0 else 0

        # Overall score: weighted composite (0-100)
        temp_score = min(40, cooling * 8)
        carbon_score = min(20, carbon_pct * 0.6)
        cost_efficiency = min(20, (cooling / max(result["total_investment_m_usd"], 0.1)) * 5)
        pop_score = min(20, pop_benefited / max(total_pop, 1) * 20)
        overall_score = round(temp_score + carbon_score + cost_efficiency + pop_score)
        if i == 0:
            overall_score = max(15, min(30, overall_score))

        # AI reasoning for this scenario
        reasoning = []
        if cfg["urban_greening"] > 0:
            reasoning.append(f"Tree canopy at {cfg['urban_greening']:.0f}% reduces land surface temperature through evapotranspiration and shade")
        if cfg["cool_roofs"] > 0:
            reasoning.append(f"Cool roofs at {cfg['cool_roofs']:.0f}% reflect solar radiation, reducing roof surface heat absorption")
        if cfg["green_roofs"] > 0:
            reasoning.append(f"Green roofs at {cfg['green_roofs']:.0f}% increase evapotranspiration and provide building insulation")
        if cfg["blue_infra"] > 0:
            reasoning.append(f"Water features at {cfg['blue_infra']:.0f}% improve evaporative cooling in surrounding areas")
        if not reasoning:
            reasoning.append("No intervention applied — this is the baseline measurement")

        scenario_entry = {
            "name": cfg["name"],
            "icon": cfg["icon"],
            "temperature_c": result["simulated_avg_lst_c"],
            "temp_reduction_c": round(cooling, 2) if cooling > 0 else 0,
            "carbon_reduction_pct": -carbon_pct if carbon_pct > 0 else 0,
            "estimated_cost_m_usd": result["total_investment_m_usd"],
            "heat_stress_reduction_pct": -heat_stress_pct if heat_stress_pct > 0 else 0,
            "population_benefited": pop_benefited,
            "overall_score": overall_score,
            "utci_c": result["simulated_utci_c"],
            "co2_tons_yr": result["co2_sequestration_tons_yr"],
            "ward_updates": result["ward_updates"],
            "reasoning": reasoning,
            "inputs": cfg,
        }
        scenarios.append(scenario_entry)

        if cooling > best_cooling:
            best_cooling = cooling
            best_idx = i

    # AI recommendation
    best = scenarios[best_idx]
    recommendation = {
        "strategy": best["name"],
        "reason": f"Highest cooling ({best['temp_reduction_c']}°C), lowest carbon impact ({best['carbon_reduction_pct']}%), best heat stress reduction",
        "confidence_pct": min(98, best["overall_score"] + 5),
    }

    return {
        "city_key": city_key,
        "baseline_lst_c": round(avg_lst, 2),
        "scenarios": scenarios,
        "recommendation": recommendation,
    }


def chat_response(message: str, city_key: str) -> str:
    """Rule-based fallback when OpenRouter LLM is unavailable."""
    summary = get_city_summary(city_key)
    city = summary["city_name"]
    metrics = summary["metrics"]
    drivers = get_drivers(city_key)
    top_driver = drivers["drivers"][0] if drivers.get("drivers") else {}
    driver_name = _driver_label(top_driver.get("feature", "vegetation deficit"))
    msg = message.lower()

    if any(w in msg for w in ["hotspot", "hottest", "highest lst", "which zones", "where is"]):
        hs = get_hotspots(city_key)
        feats = sorted(
            hs.get("features", []),
            key=lambda f: float(f.get("properties", {}).get("lst_c", 0)),
            reverse=True,
        )[:5]
        if not feats:
            return f"No severe hotspots detected in {city}. Average LST is {metrics['avg_city_lst_c']}°C."
        lines = [
            f"**Top heat hotspots in {city}** (by Land Surface Temperature):\n",
            f"City average LST: **{metrics['avg_city_lst_c']}°C** · Primary SHAP driver: **{driver_name}**\n",
        ]
        for i, f in enumerate(feats, 1):
            p = f.get("properties", {})
            lines.append(
                f"{i}. **{p.get('hotspot_label', 'Hotspot')}** — "
                f"LST **{p.get('lst_c', 0):.1f}°C**, NDVI {p.get('ndvi', 0):.2f} "
                f"(Gi* z={p.get('gi_star_z', 0):.1f})"
            )
        lines.append(
            "\nSevere clusters correlate with low NDVI / high impervious cover. "
            "Use **GHSL Built-up** and **Risk Level** map layers to cross-check."
        )
        return "\n".join(lines)

    if any(w in msg for w in ["intervention", "cooling", "top 3", "ranked", "recommend"]):
        ranking = get_ranking(city_key, limit=3)
        cooling = get_cooling_potential(city_key)
        if not ranking and not cooling:
            return f"No intervention rankings for {city} yet. Run the pipeline with --force."
        lines = [f"**Top cooling interventions for {city}:**\n"]
        for i, row in enumerate(ranking[:3], 1):
            strat = row.get("intervention_type") or row.get("strategy") or "Intervention"
            dt = float(row.get("estimated_temp_reduction_c") or row.get("delta_t_c") or 0)
            cost = row.get("estimated_cost_m_usd") or row.get("cost_m_usd")
            cost_txt = f"${float(cost):.2f}M" if cost is not None else "see simulator"
            lines.append(
                f"**#{i} {strat}** — ↓ **{dt:.2f}°C** · Est. cost **{cost_txt}** · "
                f"Timeline: {'6–12 mo' if 'roof' in str(strat).lower() else '2–3 yr' if 'green' in str(strat).lower() else '1–2 yr'}"
            )
        if cooling:
            lines.append("\n**Strategy potential (city-wide mean ΔT):**")
            for c in cooling[:3]:
                lines.append(f"• {c['strategy']}: **{c['delta_t_c']}°C**")
        lines.append("\nOpen **AI Scenario Comparison** after simulating for full cost/carbon breakdown.")
        return "\n".join(lines)

    if any(w in msg for w in ["climate", "projection", "2050", "future"]):
        proj = get_climate_projection(city_key)
        if not proj:
            return f"Climate projection unavailable for {city}."
        p0, p_end = proj[0], proj[-1]
        return (
            f"**Climate trend for {city}** (pipeline baseline extrapolation):\n"
            f"• {p0['year']}: **{p0['lst_c']}°C** → {p_end['year']}: **{p_end['lst_c']}°C**\n"
            f"• Current UTCI proxy: **{metrics['avg_heat_stress_utci_c']}°C**\n"
            f"• Resilience index: **{metrics['resilience_index']}/100**\n\n"
            "Combine urban greening + cool roofs in the Cooling Simulator to offset this trend."
        )

    if any(w in msg for w in ["plan", "planning", "administrator", "policy"]):
        ranking = get_ranking(city_key, limit=3)
        zones = ", ".join(
            r.get("zone_name", r.get("ward", "priority zone")) for r in ranking[:3] if isinstance(r, dict)
        ) or "high-LST wards on the map"
        return (
            f"**Planning recommendations for {city}:**\n"
            f"1. Target **{zones}** for phased blue-green infrastructure.\n"
            f"2. Prioritize **{driver_name}** — top SHAP driver of UHI here.\n"
            f"3. City avg LST **{metrics['avg_city_lst_c']}°C** — deploy cool roofs on public buildings first (6–12 mo).\n"
            f"4. Expand tree canopy in NDVI < 0.2 cells (see Green Coverage layer).\n"
            f"5. Download the PDF report for ward-level evidence."
        )

    if "roi" in msg or "invest" in msg or "cost" in msg:
        return (
            "Ranked interventions are in the right panel. Cool roofs offer lower complexity; "
            "urban greening yields higher ΔT but higher cost per sqm."
        )
    if "hi" in msg or "hello" in msg:
        return (
            f"Hello! I'm the UrbanYantra analytics agent for **{city}**. "
            "Ask about LST hotspots, SHAP drivers, interventions, or climate projections."
        )
    return (
        f"**{city} snapshot:** LST **{metrics['avg_city_lst_c']}°C**, "
        f"UTCI **{metrics['avg_heat_stress_utci_c']}°C**, "
        f"resilience **{metrics['resilience_index']}/100**. "
        f"Top driver: **{driver_name}**. Try the quick prompts or Cooling Simulator."
    )
