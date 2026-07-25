"""Optional IBM Granite LST hourly gap-filling (modular add-on)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def densify_lst_temporal(config: dict, out_dir) -> None:
    if not config.get("enable_granite", False):
        logger.info("IBM Granite LST skipped. Enable when temporal density is required.")
        return
    logger.warning("Granite integration not bundled — add granite-lst model hook for hourly LST.")
