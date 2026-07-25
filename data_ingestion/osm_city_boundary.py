"""Fetch OSM city / district footprint and clip raster pixels to it."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box, mapping
from shapely.ops import unary_union

logger = logging.getLogger(__name__)


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def _bbox_tuple(bbox: list[float]) -> tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    return (min_lon, min_lat, max_lon, max_lat)


def _name_matches(city_name: str, feature_name: str) -> bool:
    city = _normalize_name(city_name)
    raw = _normalize_name(feature_name)
    if not city or not raw:
        return False
    aliases = {city}
    if city == "bengaluru":
        aliases.update({"bangalore", "bengaluruurban", "bruhatbengalurumahanagarapalike", "bbmp"})
    if city == "delhincr":
        aliases.update({"delhi", "newdelhi", "ncr"})
    if city == "mangaluru":
        aliases.update({"mangalore"})
    if city == "visakhapatnam":
        aliases.update({"vizag", "visakhapatnam"})
    return any(a in raw or raw in a for a in aliases)


def _clip_to_bbox(geom, bbox: list[float]):
    clip = box(bbox[0], bbox[1], bbox[2], bbox[3])
    g = geom.intersection(clip)
    return g if not g.is_empty else None


def _fetch_geocode_boundary(city_name: str, state: str, bbox: list[float]):
    try:
        import osmnx as ox

        for query in (f"{city_name}, {state}, India", f"{city_name}, India"):
            try:
                gdf = ox.geocode_to_gdf(query)
            except Exception:
                continue
            if gdf.empty:
                continue
            geom = unary_union(gdf.geometry)
            clipped = _clip_to_bbox(geom, bbox)
            if clipped and not clipped.is_empty:
                logger.info("City boundary from geocode: %s", query)
                return clipped
    except Exception as exc:
        logger.warning("Geocode boundary failed (%s)", exc)
    return None


def _fetch_admin_boundary(city_name: str, bbox: list[float]):
    try:
        import osmnx as ox

        ox.settings.use_cache = True
        ox.settings.log_console = False
        polys = []
        for level in ("6", "7", "8"):
            gdf = ox.features_from_bbox(
                bbox=_bbox_tuple(bbox),
                tags={"boundary": "administrative", "admin_level": level},
            )
            if gdf.empty:
                continue
            gdf = gdf.reset_index(drop=True)
            if "name" not in gdf.columns:
                continue
            gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
            matched = gdf[gdf["name"].apply(lambda n: _name_matches(city_name, n))]
            if not matched.empty:
                polys.extend(matched.geometry)
        if polys:
            geom = unary_union(polys)
            clipped = _clip_to_bbox(geom, bbox)
            if clipped and not clipped.is_empty:
                logger.info("City boundary from admin polygon (%d parts)", len(polys))
                return clipped
    except Exception as exc:
        logger.warning("Admin boundary fetch failed (%s)", exc)
    return None


def _fetch_district_union(bbox: list[float]):
    """Union suburb / neighbourhood / ward polygons inside the study bbox."""
    try:
        import osmnx as ox

        ox.settings.use_cache = True
        ox.settings.log_console = False
        parts = []
        for tags in (
            {"place": ["suburb", "neighbourhood", "quarter", "town"]},
            {"boundary": "administrative", "admin_level": ["9", "10"]},
        ):
            gdf = ox.features_from_bbox(bbox=_bbox_tuple(bbox), tags=tags)
            if gdf.empty:
                continue
            gdf = gdf.reset_index(drop=True)
            gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
            if not gdf.empty:
                parts.extend(gdf.geometry)
        if len(parts) < 3:
            return None
        geom = unary_union(parts)
        clipped = _clip_to_bbox(geom, bbox)
        if clipped and not clipped.is_empty:
            logger.info("City boundary from OSM district union (%d polygons)", len(parts))
            return clipped
    except Exception as exc:
        logger.warning("District union fetch failed (%s)", exc)
    return None


def _simplify_boundary(geom, bbox: list[float]):
    """Light simplification so point-in-polygon stays fast on large metros."""
    clip = box(bbox[0], bbox[1], bbox[2], bbox[3])
    g = geom.intersection(clip)
    if g.is_empty:
        return None
    try:
        return g.simplify(0.00035, preserve_topology=True)
    except Exception:
        return g


def _score_boundary(df: pd.DataFrame, geom, source: str) -> tuple[object, float] | None:
    from shapely.geometry import Point

    total = len(df)
    if total == 0:
        return None
    trial = mask_pixels_to_boundary(df, geom)
    visible = int((~trial["is_excluded"]).sum())
    ratio = visible / total
    if ratio < 0.12:
        logger.info("Skip %s boundary — only %.1f%% visible", source, ratio * 100)
        return None
    if ratio > 0.92:
        logger.info("Skip %s boundary — too rectangular (%.1f%% visible)", source, ratio * 100)
        return None
    logger.info("Candidate %s boundary — %.1f%% visible", source, ratio * 100)
    return geom, ratio


def fetch_city_boundary_geometry(config: dict, df: pd.DataFrame | None = None) -> object | None:
    """Best-effort OSM city / district outline for pixel clipping."""
    city_name = config.get("city_name", "")
    state = config.get("state", "India")
    bbox = config["bbox"]
    center_lon = (bbox[0] + bbox[2]) / 2
    center_lat = (bbox[1] + bbox[3]) / 2
    from shapely.geometry import Point

    center = Point(center_lon, center_lat)

    def _valid(geom):
        if geom is None or geom.is_empty:
            return None
        g = _simplify_boundary(geom, bbox)
        if g is None or not g.intersects(center):
            return None
        return g

    if df is None or df.empty:
        for geom in (
            _fetch_district_union(bbox),
            _fetch_admin_boundary(city_name, bbox),
            _fetch_geocode_boundary(city_name, state, bbox),
        ):
            g = _valid(geom)
            if g is not None:
                return g
        return None

    best_geom = None
    best_ratio = 1.0
    district_fallback = None
    for source, raw in (
        ("district_union", _fetch_district_union(bbox)),
        ("admin", _fetch_admin_boundary(city_name, bbox)),
        ("geocode", _fetch_geocode_boundary(city_name, state, bbox)),
    ):
        geom = _valid(raw)
        if geom is None:
            continue
        if source == "district_union":
            district_fallback = geom
        scored = _score_boundary(df, geom, source)
        if scored is None:
            continue
        geom, ratio = scored
        if ratio < best_ratio:
            best_ratio = ratio
            best_geom = geom

    if best_geom is not None:
        return best_geom

    # Tight bboxes (e.g. Pune): still use OSM district union if it covers enough pixels.
    if district_fallback is not None:
        trial = mask_pixels_to_boundary(df, district_fallback)
        ratio = (~trial["is_excluded"]).mean()
        if ratio >= 0.12:
            logger.info("Fallback to district_union boundary — %.1f%% visible", ratio * 100)
            return district_fallback

    return None


def ingest_city_boundary(
    config: dict,
    out_dir: Path,
    df: pd.DataFrame | None = None,
    geom: object | None = None,
) -> Path | None:
    """Download and cache city footprint GeoJSON."""
    out_path = out_dir / "geojson" / "city_boundary.geojson"
    if out_path.exists() and not config.get("force_refresh") and geom is None:
        return out_path

    if geom is None:
        geom = fetch_city_boundary_geometry(config, df=df)
    if geom is None:
        logger.warning("No OSM city boundary for %s", config.get("city_name"))
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(
        [{"name": config.get("city_name", "city"), "source": "osm", "geometry": geom}],
        crs="EPSG:4326",
    )
    gdf.to_file(out_path, driver="GeoJSON")
    meta = {"city": config.get("city_name"), "source": "osm", "area_deg2": float(geom.area)}
    (out_dir / "geojson" / "city_boundary_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    logger.info("City boundary saved: %s", out_path)
    return out_path


def load_city_boundary_geometry(out_dir: Path):
    path = out_dir / "geojson" / "city_boundary.geojson"
    if not path.exists():
        return None
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    if gdf.empty:
        return None
    return unary_union(gdf.geometry)


def mask_pixels_to_boundary(df: pd.DataFrame, boundary_geom) -> pd.DataFrame:
    """Mark pixels outside the OSM district outline as excluded."""
    if df.empty or boundary_geom is None:
        return df

    from shapely.geometry import Point
    from shapely.prepared import prep

    prepared = prep(boundary_geom)
    in_boundary = [
        prepared.contains(Point(float(lon), float(lat))) for lon, lat in zip(df["lon"], df["lat"])
    ]

    out = df.copy()
    water = out["is_water"].to_numpy(dtype=bool) if "is_water" in out.columns else False
    out["is_excluded"] = (~np.array(in_boundary)) | water

    visible = int((~out["is_excluded"]).sum())
    logger.info(
        "OSM boundary mask: %d / %d pixels visible (%.1f%% excluded)",
        visible,
        len(out),
        out["is_excluded"].mean() * 100,
    )
    return out


def verify_pixels_inside_boundary(df: pd.DataFrame, out_dir: Path) -> dict:
    """Audit: every visible pixel should lie inside the cached OSM boundary."""
    from shapely.geometry import Point
    from shapely.prepared import prep

    boundary = load_city_boundary_geometry(out_dir)
    if boundary is None:
        return {"ok": False, "reason": "no_boundary_file"}

    visible = df[~df["is_excluded"]] if "is_excluded" in df.columns else df
    if visible.empty:
        return {"ok": True, "visible": 0, "outside": 0}

    prepared = prep(boundary)
    outside = sum(
        1
        for lon, lat in zip(visible["lon"], visible["lat"])
        if not prepared.contains(Point(float(lon), float(lat)))
    )
    return {
        "ok": outside == 0,
        "visible": len(visible),
        "outside": outside,
        "has_boundary": True,
    }


def boundary_geojson_dict(out_dir: Path) -> dict | None:
    """Return city boundary as GeoJSON FeatureCollection for map overlay (optional)."""
    path = out_dir / "geojson" / "city_boundary.geojson"
    if not path.exists():
        return None
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    features = []
    for _, row in gdf.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(row.geometry),
                "properties": {"name": row.get("name", ""), "source": row.get("source", "osm")},
            }
        )
    return {"type": "FeatureCollection", "features": features}
