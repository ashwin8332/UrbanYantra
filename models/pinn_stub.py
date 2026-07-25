"""Optional PINN branch — heat-diffusion inspired regularization (modular add-on)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def train_pinn(config: dict, df, out_dir) -> None:
    if not config.get("enable_pinn", False):
        logger.info("PINN skipped. Set enable_pinn=true after baseline is stable.")
        return
    logger.warning("PINN requires torch. Implement energy-balance loss as follow-on module.")
