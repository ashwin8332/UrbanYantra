"""Fetch OSM neighborhood / administrative polygons; Voronoi fallback from ward seeds."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from data_ingestion.osm_city_boundary import load_city_boundary_geometry
from features.display_pixels import visible_pixels
from geography.ward_seeds import WARD_COORDINATES

logger = logging.getLogger(__name__)


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _bbox_tuple(bbox: list[float]) -> tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    return (min_lon, min_lat, max_lon, max_lat)


def _fetch_osm_place_polygons(bbox: list[float]) -> gpd.GeoDataFrame:
    try:
        import osmnx as ox

        ox.settings.use_cache = True
        ox.settings.log_console = False
        gdf = ox.features_from_bbox(
            bbox=_bbox_tuple(bbox),
            tags={"place": ["suburb", "neighbourhood", "quarter", "town"]},
        )
        if gdf.empty:
            return gpd.GeoDataFrame(columns=["name", "geometry"], crs="EPSG:4326")
        gdf = gdf.reset_index(drop=True)
        if "name" not in gdf.columns:
            gdf["name"] = gdf.index.astype(str)
        gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
        logger.info("OSM place polygons: %d features", len(gdf))
        return gdf[["name", "geometry"]].to_crs("EPSG:4326")
    except Exception as exc:
        logger.warning("OSM place fetch failed (%s)", exc)
        return gpd.GeoDataFrame(columns=["name", "geometry"], crs="EPSG:4326")


def _fetch_osm_admin_polygons(bbox: list[float]) -> gpd.GeoDataFrame:
    try:
        import osmnx as ox

        gdf = ox.features_from_bbox(
            bbox=_bbox_tuple(bbox),
            tags={"boundary": "administrative", "admin_level": ["9", "10"]},
        )
        if gdf.empty:
            return gpd.GeoDataFrame(columns=["name", "geometry"], crs="EPSG:4326")
        gdf = gdf.reset_index(drop=True)
        if "name" not in gdf.columns:
            gdf["name"] = gdf.index.astype(str)
        gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
        logger.info("OSM admin polygons: %d features", len(gdf))
        return gdf[["name", "geometry"]].to_crs("EPSG:4326")
    except Exception as exc:
        logger.warning("OSM admin fetch failed (%s)", exc)
        return gpd.GeoDataFrame(columns=["name", "geometry"], crs="EPSG:4326")


def _voronoi_wards(city_name: str, bbox: list[float]) -> gpd.GeoDataFrame:
    seeds = WARD_COORDINATES.get(city_name, {})
    if not seeds:
        return gpd.GeoDataFrame(columns=["name", "geometry", "source"], crs="EPSG:4326")

    min_lon, min_lat, max_lon, max_lat = bbox
    # Drop seeds outside the study bbox — avoids huge sea-spanning Voronoi cells
    seeds = {
        name: (lat, lon)
        for name, (lat, lon) in seeds.items()
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
    }
    if not seeds:
        return gpd.GeoDataFrame(columns=["name", "geometry", "source"], crs="EPSG:4326")

    clip = box(min_lon, min_lat, max_lon, max_lat)
    names = list(seeds.keys())
    lons = [seeds[n][1] for n in names]
    lats = [seeds[n][0] for n in names]

    gdf_pts = gpd.GeoDataFrame(
        {"name": names},
        geometry=gpd.points_from_xy(lons, lats),
        crs="EPSG:4326",
    )
    utm = gdf_pts.to_crs(32643)
    clip_utm = gpd.GeoSeries([clip], crs="EPSG:4326").to_crs(32643).iloc[0]
    vor = utm.geometry.voronoi_polygons(extend_to=clip_utm.envelope)
    ward_gdf = gpd.GeoDataFrame({"name": names, "geometry": vor}, crs=32643)
    ward_gdf = ward_gdf.to_crs("EPSG:4326")
    ward_gdf["geometry"] = ward_gdf.geometry.intersection(clip)
    ward_gdf = ward_gdf[~ward_gdf.geometry.is_empty].copy()
    ward_gdf["source"] = "voronoi_seeds"
    return ward_gdf


def _match_osm_to_seeds(osm_gdf: gpd.GeoDataFrame, city_name: str) -> gpd.GeoDataFrame:
    seeds = WARD_COORDINATES.get(city_name, {})
    if osm_gdf.empty or not seeds:
        return gpd.GeoDataFrame(columns=["name", "geometry", "source"], crs="EPSG:4326")

    norm_seeds = {_normalize_name(k): k for k in seeds}
    rows = []
    for _, row in osm_gdf.iterrows():
        raw = str(row.get("name", ""))
        key = _normalize_name(raw)
        matched = None
        if key in norm_seeds:
            matched = norm_seeds[key]
        else:
            for nk, canonical in norm_seeds.items():
                if nk in key or key in nk:
                    matched = canonical
                    break
        if matched:
            rows.append({"name": matched, "geometry": row.geometry, "source": "osm"})
    if not rows:
        return gpd.GeoDataFrame(columns=["name", "geometry", "source"], crs="EPSG:4326")
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def clip_ward_boundaries_to_land(df, ward_path: Path) -> None:
    """Clip ward polygons to the city footprint (OSM boundary or land pixels)."""
    import geopandas as gpd

    if not ward_path.exists() or df is None or len(df) == 0:
        return

    wards = gpd.read_file(ward_path).to_crs("EPSG:4326")
    out_dir = ward_path.parent.parent
    outline = load_city_boundary_geometry(out_dir)
    if outline is None:
        land = visible_pixels(df)
        if land.empty:
            return
        pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(land["lon"], land["lat"]), crs="EPSG:4326")
        outline = pts.union_all().convex_hull

    wards["geometry"] = wards.geometry.intersection(outline)
    wards = wards[~wards.geometry.is_empty].copy()
    wards.to_file(ward_path, driver="GeoJSON")
    logger.info("Ward boundaries clipped to land footprint (%d wards)", len(wards))


def ingest_ward_boundaries(config: dict, out_dir: Path, df=None) -> Path:
    out_path = out_dir / "geojson" / "ward_boundaries.geojson"
    if out_path.exists() and not config.get("force_refresh"):
        return out_path

    city = config.get("city_name", "city")
    bbox = config["bbox"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    osm_places = _fetch_osm_place_polygons(bbox)
    osm_admin = _fetch_osm_admin_polygons(bbox)
    osm_all = pd.concat([osm_places, osm_admin], ignore_index=True) if len(osm_places) or len(osm_admin) else osm_places
    matched = _match_osm_to_seeds(osm_all, city)
    voronoi = _voronoi_wards(city, bbox)

    if matched.empty:
        final = voronoi
        logger.info("Using Voronoi ward tessellation (%d wards)", len(final))
    else:
        matched_names = set(matched["name"])
        fill = voronoi[~voronoi["name"].isin(matched_names)]
        final = pd.concat([matched, fill], ignore_index=True)
        final = gpd.GeoDataFrame(final, crs="EPSG:4326")
        logger.info("Wards: %d OSM + %d Voronoi fill", len(matched), len(fill))

    final["ward_id"] = final["name"].str.lower().str.replace(" ", "_", regex=False)
    final = final.dissolve(by="name", aggfunc={"source": "first", "ward_id": "first"}).reset_index()
    final.to_file(out_path, driver="GeoJSON")

    if df is not None:
        clip_ward_boundaries_to_land(df, out_path)

    meta = {"city": city, "source": final["source"].value_counts().to_dict(), "ward_count": int(len(final))}
    (out_dir / "geojson" / "ward_boundaries_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("Ward boundaries saved: %s", out_path)
    return out_path
