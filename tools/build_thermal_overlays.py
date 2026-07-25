#!/usr/bin/env python3
"""Build georeferenced thermal satellite overlays for all cities with pipeline data."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.thermal_overlay import build_thermal_overlay
from utils import list_city_keys, load_city_config


def main() -> int:
    cities_yaml = ROOT / "configs" / "cities.yaml"
    keys = list_city_keys(cities_yaml)
    built, skipped, failed = 0, 0, 0

    for key in keys:
        cfg = load_city_config(cities_yaml, key)
        out_dir = ROOT / cfg["output_dir"]
        if not (out_dir / "tables" / "feature_table.parquet").exists():
            print(f"  skip {key}: no pipeline output")
            skipped += 1
            continue
        try:
            meta = build_thermal_overlay(key, force=True)
            print(
                f"  ok {key}: {meta['width']}x{meta['height']} "
                f"LST {meta['vmin_k']}-{meta['vmax_k']} K"
            )
            built += 1
        except Exception as exc:
            print(f"  FAIL {key}: {exc}")
            failed += 1

    print(f"\nDone: {built} built, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
