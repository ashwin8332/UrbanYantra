"""Helpers to enforce real-data-only runs when data_mode is gee or local."""

from __future__ import annotations


def is_real_data_mode(config: dict) -> bool:
    return config.get("data_mode", "synthetic") in ("gee", "local")


def is_local_data_mode(config: dict) -> bool:
    return config.get("data_mode", "synthetic") == "local"


def use_gee_for_satellite(config: dict) -> bool:
    """Satellite rasters (Landsat, S2, WorldCover) come from GEE in both gee and local modes."""
    return config.get("data_mode", "synthetic") in ("gee", "local")


def prefer_local_files(config: dict) -> bool:
    if is_local_data_mode(config):
        return True
    if bool((config.get("local_data") or {}).get("prefer_local_over_gee", False)):
        return True
    if (config.get("remote_data") or {}).get("urban_dataset_folder"):
        return True
    return False


def require_real_source(config: dict, source: str, exc: Exception | None = None) -> None:
    """Raise when a real data source fails in gee/local mode (no synthetic substitute)."""
    if not is_real_data_mode(config):
        return
    detail = f": {exc}" if exc else ""
    raise RuntimeError(
        f"Real data required for '{source}' (data_mode={config.get('data_mode')}) but fetch failed{detail}. "
        "Check configs/local_datasets.yaml paths, Hugging Face repo access, GEE auth, and re-run with --force"
    ) from exc
