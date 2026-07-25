#!/usr/bin/env python3
"""Validate multi-city config bboxes (Phase 0 acceptance check)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def validate_bbox(bbox: list[float], name: str) -> list[str]:
    errors = []
    if len(bbox) != 4:
        return [f"{name}: bbox must have 4 values [min_lon, min_lat, max_lon, max_lat]"]
    min_lon, min_lat, max_lon, max_lat = bbox
    if not (-180 <= min_lon < max_lon <= 180):
        errors.append(f"{name}: invalid longitude range {bbox}")
    if not (-90 <= min_lat < max_lat <= 90):
        errors.append(f"{name}: invalid latitude range {bbox}")
    if (max_lon - min_lon) < 0.02 or (max_lat - min_lat) < 0.02:
        errors.append(f"{name}: bbox too small for city-scale analysis")
    return errors


def main() -> int:
    path = ROOT / "configs" / "cities.yaml"
    if not path.exists():
        print(f"ERROR: missing {path}")
        return 1

    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    cities = cfg.get("cities", {})
    if not cities:
        print("ERROR: no cities defined")
        return 1

    all_errors: list[str] = []
    print(f"Validating {len(cities)} cities from {path.name}...")
    for key, city_cfg in cities.items():
        bbox = city_cfg.get("bbox")
        if bbox is None:
            all_errors.append(f"{key}: missing bbox")
            continue
        errs = validate_bbox(bbox, key)
        all_errors.extend(errs)
        if not errs:
            stations = city_cfg.get("stations", [])
            print(f"  OK  {key:12s}  bbox={bbox}  stations={len(stations)}")

    if all_errors:
        print("\nValidation FAILED:")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    print("\nAll city bboxes valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
