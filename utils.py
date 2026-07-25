"""Urban heat mitigation pipeline — shared utilities."""

from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_city_config(cities_path: str | Path, city_key: str) -> dict[str, Any]:
    """Merge defaults + per-city entry from configs/cities.yaml + local_datasets.yaml."""
    raw = load_config(cities_path)
    defaults = deepcopy(raw.get("defaults", {}))
    city = raw["cities"][city_key]
    merged = {**defaults, **city}
    merged["city_key"] = city_key

    local_path = Path(cities_path).parent / "local_datasets.yaml"
    if local_path.exists():
        local_raw = load_config(local_path)
        local_data = local_raw.get("local_data", {})
        merged.setdefault("local_data", {})
        merged["local_data"] = {**local_data, **merged.get("local_data", {})}

    remote_path = Path(cities_path).parent / "remote_datasets.yaml"
    if remote_path.exists():
        remote_raw = load_config(remote_path)
        remote_data = remote_raw.get("remote_data", {})
        merged.setdefault("remote_data", {})
        merged["remote_data"] = {**remote_data, **merged.get("remote_data", {})}

    return merged


def list_city_keys(cities_path: str | Path) -> list[str]:
    raw = load_config(cities_path)
    return list(raw.get("cities", {}).keys())


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def grid_shape_from_bbox(
    bbox: list[float],
    resolution_m: float = 10,
    max_side: int | None = None,
) -> tuple[int, int]:
    """Pixel grid (height, width) for a WGS84 bbox at the given ground resolution."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_mid = (min_lat + max_lat) / 2.0
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat_mid))
    w = max(1, int(round((max_lon - min_lon) * m_per_deg_lon / resolution_m)))
    h = max(1, int(round((max_lat - min_lat) * m_per_deg_lat / resolution_m)))
    if max_side and max(h, w) > max_side:
        scale = max_side / max(h, w)
        h = max(1, int(round(h * scale)))
        w = max(1, int(round(w * scale)))
    return h, w


def synthetic_grid_shape(config: dict[str, Any]) -> tuple[int, int]:
    """Consistent synthetic grid size — capped for fast local/hackathon runs."""
    max_side = int(config.get("synthetic_max_grid_side", 120))
    return grid_shape_from_bbox(
        config["bbox"],
        config.get("target_resolution_m", 10),
        max_side=max_side,
    )
