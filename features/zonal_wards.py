"""Zonal statistics — aggregate pixel features per ward polygon."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import mapping

from features.display_pixels import visible_pixels

logger = logging.getLogger(__name__)


def _approx_utci(lst_c: float, humidity: float = 0.55) -> float:
    return float(lst_c * 0.72 + humidity * 8.0 - 2.5)


def _vulnerability(avg_lst: float, hotspot_frac: float) -> str:
    if avg_lst >= 42 or hotspot_frac > 0.35:
        return "CRITICAL"
    if avg_lst >= 40 or hotspot_frac > 0.2:
        return "HIGH"
    if avg_lst >= 38:
        return "MODERATE"
    return "LOW"


def build_ward_zonal_geojson(
    config: dict,
    df: pd.DataFrame,
    out_dir: Path,
    city_key: str,
) -> dict[str, Any]:
    """
    Point-in-polygon zonal stats per ward boundary polygon.
    Writes geojson/ward_zonal.geojson for API domains layer.
    """
    ward_path = out_dir / "geojson" / "ward_boundaries.geojson"
    out_path = out_dir / "geojson" / "ward_zonal.geojson"
    if not ward_path.exists():
        raise FileNotFoundError(f"Missing ward boundaries: {ward_path}. Run ward ingestion first.")

    wards = gpd.read_file(ward_path).to_crs("EPSG:4326")
    land = visible_pixels(df)
    gdf_pts = gpd.GeoDataFrame(
        land,
        geometry=gpd.points_from_xy(land["lon"], land["lat"]),
        crs="EPSG:4326",
    )

    joined = gpd.sjoin(gdf_pts, wards, how="inner", predicate="within")
    if joined.empty:
        joined = _nearest_ward_join(gdf_pts, wards)

    lst_col = "lst_calibrated_c" if "lst_calibrated_c" in joined.columns else "lst_c"
    agg_spec: dict = {
        "avg_lst_c": (lst_col, "mean"),
        "raw_lst_c": ("lst_c", "mean"),
        "avg_ndvi": ("ndvi", "mean"),
        "avg_ndbi": ("ndbi", "mean"),
        "hotspot_fraction": ("hotspot_class", lambda s: float((s >= 1).mean())),
    }
    if "humidity_proxy" in joined.columns:
        agg_spec["humidity_proxy"] = ("humidity_proxy", "mean")
    agg = joined.groupby("name", sort=False).agg(**agg_spec).reset_index()

    features = []
    for _, row in agg.iterrows():
        name = str(row["name"])
        ward_row = wards[wards["name"] == name]
        if ward_row.empty:
            continue
        geom = ward_row.iloc[0].geometry
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)

        avg_lst = float(row["avg_lst_c"])
        raw_lst = float(row.get("raw_lst_c", avg_lst))
        humidity = float(row["humidity_proxy"]) if "humidity_proxy" in row.index and pd.notna(row["humidity_proxy"]) else 0.55
        hotspot_frac = float(row["hotspot_fraction"])
        ward_id = f"{city_key}_{name.lower().replace(' ', '_')}"

        features.append(
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {
                    "ward_id": ward_id,
                    "name": name,
                    "avg_lst_c": round(raw_lst, 2),
                    "lst_calibrated_c": round(avg_lst, 2),
                    "simulated_lst_c": round(avg_lst, 2),
                    "heat_stress_utci_c": round(_approx_utci(avg_lst, humidity), 2),
                    "cooling_delta_c": 0.0,
                    "ndvi": round(float(row["avg_ndvi"]), 3),
                    "ndbi": round(float(row["avg_ndbi"]), 3),
                    "vulnerability_class": _vulnerability(avg_lst, hotspot_frac),
                    "hotspot_fraction": round(hotspot_frac, 3),
                    "boundary_source": str(ward_row.iloc[0].get("source", "osm")),
                },
            }
        )

    collection = {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ward_count": len(features),
            "zonal_method": "point_in_polygon",
            "lst_field": lst_col,
        },
    }
    out_path.write_text(json.dumps(collection), encoding="utf-8")
    logger.info("Ward zonal GeoJSON: %d wards → %s", len(features), out_path)
    return collection


def _nearest_ward_join(points: gpd.GeoDataFrame, wards: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Fallback when strict within-join yields no matches."""
    wards = wards.copy()
    wards["centroid"] = wards.geometry.centroid
    rows = []
    for _, pt in points.iterrows():
        dist = wards["centroid"].distance(pt.geometry)
        best = wards.loc[dist.idxmin()]
        rec = pt.to_dict()
        rec["name"] = best["name"]
        rec["index_right"] = dist.idxmin()
        rows.append(rec)
    return gpd.GeoDataFrame(rows, geometry=gpd.points_from_xy([r["lon"] for r in rows], [r["lat"] for r in rows]), crs="EPSG:4326")
