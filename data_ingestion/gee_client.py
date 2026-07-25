"""Google Earth Engine client with graceful fallback."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_gee_initialized = False
_gee_project: str | None = None


def resolve_gee_project(project: str | None = None, config: dict[str, Any] | None = None) -> str | None:
    """Project ID: explicit arg > config > GEE_PROJECT env."""
    if project:
        return project
    if config:
        cfg_project = config.get("gee_project")
        if cfg_project:
            return str(cfg_project)
    env_project = os.environ.get("GEE_PROJECT")
    return env_project or None


def init_gee(project: str | None = None, config: dict[str, Any] | None = None) -> bool:
    """Initialize GEE. Returns True if successful."""
    global _gee_initialized, _gee_project
    resolved = resolve_gee_project(project, config)
    if _gee_initialized and (resolved is None or resolved == _gee_project):
        return True
    try:
        import ee

        if resolved:
            ee.Initialize(project=resolved)
            _gee_project = resolved
            logger.info("Google Earth Engine initialized (project=%s).", resolved)
        else:
            ee.Initialize()
            logger.info("Google Earth Engine initialized (default project).")
        _gee_initialized = True
        return True
    except Exception as exc:
        logger.warning(
            "GEE init failed (%s). Set gee_project in config, GEE_PROJECT env, or run: earthengine authenticate",
            exc,
        )
        return False


def get_study_region(bbox: list[float]):
    """Return ee.Geometry.Rectangle from [min_lon, min_lat, max_lon, max_lat]."""
    import ee

    return ee.Geometry.Rectangle(bbox)
