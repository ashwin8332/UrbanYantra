"""Tests for urban heat mitigation pipeline."""

import numpy as np
import pytest

from features.spectral_indices import compute_indices_from_bands
from preprocessing.lst_downscale import downscale_lst
from simulation.invest_ucm import invest_ucm_delta_t


def test_spectral_indices_ranges():
    bands = {
        "B3": np.full((10, 10), 0.2),
        "B4": np.full((10, 10), 0.15),
        "B8": np.full((10, 10), 0.4),
        "B11": np.full((10, 10), 0.25),
    }
    idx = compute_indices_from_bands(bands)
    assert "ndvi" in idx
    assert idx["ndvi"].shape == (10, 10)
    assert np.all(idx["ndvi"] >= -1) and np.all(idx["ndvi"] <= 1)


def test_lst_downscale_shape():
    coarse = np.random.rand(30, 30).astype(np.float32) * 5 + 32
    ndvi = np.random.rand(60, 60).astype(np.float32)
    ndbi = np.random.rand(60, 60).astype(np.float32)
    out = downscale_lst(coarse, ndvi, ndbi)
    assert out.shape == (60, 60)


def test_invest_ucm_cooling_sign():
    lst = np.full((5, 5), 38.0)
    ndvi = np.zeros((5, 5))
    imp = np.ones((5, 5))
    delta = invest_ucm_delta_t(lst, ndvi, imp, "urban_greening", {"canopy_increase_pct": 25, "shade_factor": 0.15})
    assert np.all(delta < 0)


def test_getis_ord_hotspot_shape():
    from features.hotspot_detection import getis_ord_gi_star

    grid = np.random.rand(20, 20).astype(np.float32) * 5 + 32
    z, p = getis_ord_gi_star(grid, kernel_size=5)
    assert z.shape == grid.shape
    assert p.shape == grid.shape


def test_lcz_proxy_range():
    from features.lcz_proxy import derive_lcz_proxy

    h = np.array([[0, 25], [50, 10]], dtype=np.float32)
    imp = np.array([[0.1, 0.9], [0.8, 0.3]], dtype=np.float32)
    lcz = derive_lcz_proxy(h, imp)
    assert lcz.min() >= 1 and lcz.max() <= 10


def test_grid_shape_from_bbox():
    from utils import grid_shape_from_bbox, synthetic_grid_shape

    h, w = grid_shape_from_bbox([73.80, 18.48, 73.92, 18.58], resolution_m=10, max_side=120)
    assert h <= 120 and w <= 120
    assert h >= 1 and w >= 1

    cfg = {"bbox": [72.75, 18.89, 72.98, 19.27], "target_resolution_m": 10}
    sh, sw = synthetic_grid_shape(cfg)
    assert sh == sw == 120


def test_resize_to_match():
    from features.build_feature_table import _resize_to_match

    coarse = np.arange(9, dtype=np.float32).reshape(3, 3)
    out = _resize_to_match(coarse, (6, 6))
    assert out.shape == (6, 6)
