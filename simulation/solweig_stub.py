"""
SOLWEIG + TreePlanter stub — modular hook for physics-based thermal comfort.

Full SOLWEIG requires 3D city models (see VoxCity). Enable when UMEP/SOLWEIG
is installed: https://github.com/UMEP-dev/solweig

This stub documents the interface and returns None when not configured.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run_solweig_treeplanter(config: dict, out_dir) -> dict | None:
    """Optional pedestrian thermal comfort simulation."""
    if not config.get("enable_solweig", False):
        logger.info("SOLWEIG/TreePlanter skipped (enable_solweig=false). Modular add-on.")
        return None
    logger.warning("SOLWEIG not bundled — install UMEP/solweig and VoxCity for 3D workflows.")
    return None
