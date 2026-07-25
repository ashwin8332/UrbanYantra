"""Download datasets from Hugging Face / URLs into a shared cache (works on Render, CI, any machine)."""

from __future__ import annotations

import logging
import os
import zipfile
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "data" / "cache"
BENCHMARKS_DIR = ROOT / "data" / "benchmarks"


def _cache_root(config: dict) -> Path:
    raw = (config.get("remote_data") or {}).get("cache_dir") or os.environ.get("URBANYANTRA_DATA_CACHE", "")
    path = Path(str(raw)).expanduser() if raw else DEFAULT_CACHE
    path.mkdir(parents=True, exist_ok=True)
    return path


def _urban_hf_repo(config: dict) -> tuple[str, str] | None:
    remote = config.get("remote_data") or {}
    for key in ("urban_dataset_folder", "ghsl_drive_root"):
        block = remote.get(key) or {}
        repo_id = block.get("huggingface_repo_id") or block.get("hf_repo_id")
        if repo_id:
            revision = block.get("huggingface_revision") or block.get("hf_revision") or "main"
            return str(repo_id), str(revision)
    return None


def sync_huggingface_dataset(
    repo_id: str,
    dest: Path,
    *,
    revision: str = "main",
    force: bool = False,
) -> Path:
    """Download a public Hugging Face dataset repo into a local cache directory."""
    dest = Path(dest)
    marker = dest / ".hf_sync_ok"
    if marker.exists() and not force and any(dest.rglob("*")):
        logger.info("Hugging Face dataset cached → %s", dest)
        return dest

    dest.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download

        logger.info(
            "Syncing Hugging Face dataset %s@%s → %s (may take several minutes)",
            repo_id,
            revision,
            dest,
        )
        snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            revision=revision,
            local_dir=str(dest),
        )
        marker.write_text(f"{repo_id}@{revision}", encoding="utf-8")
        logger.info("Hugging Face sync complete: %s files", len(list(dest.rglob("*"))))
    except Exception as exc:
        raise RuntimeError(
            f"Hugging Face dataset sync failed for {repo_id}. "
            "Ensure the repo is public and huggingface_hub is installed."
        ) from exc
    return dest


def ensure_urban_dataset_cached(config: dict, *, force: bool = False) -> Path:
    """Download Urban Dataset from Hugging Face once → data/cache/urban_dataset/."""
    hf = _urban_hf_repo(config)
    if not hf:
        raise FileNotFoundError(
            "Set remote_data.urban_dataset_folder.huggingface_repo_id in configs/remote_datasets.yaml"
        )
    repo_id, revision = hf
    cache = _cache_root(config) / "urban_dataset"
    marker = cache / ".sync_complete"
    if marker.exists() and not force and any(cache.rglob("*.zip")):
        return cache
    sync_huggingface_dataset(repo_id, cache, revision=revision, force=force)
    marker.write_text(f"{repo_id}@{revision}", encoding="utf-8")
    return cache


def _download_bytes(url: str, timeout: int = 300) -> bytes:
    session = requests.Session()
    resp = session.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    return resp.content


def download_to_cache(
    url: str,
    dest: Path,
    *,
    force: bool = False,
    extract_zip: bool = False,
) -> Path:
    dest = Path(dest)
    if dest.exists() and not force:
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading → %s", dest.name)
    content = _download_bytes(url)
    dest.write_bytes(content)

    if extract_zip and zipfile.is_zipfile(dest):
        extract_dir = dest.with_suffix("")
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest) as zf:
            zf.extractall(extract_dir)
        logger.info("Extracted zip → %s", extract_dir)
        return extract_dir

    return dest


def resolve_dataset(
    config: dict,
    key: str,
    *,
    force: bool = False,
) -> Path | None:
    """
    Resolve a dataset path with priority:
    1. Bundled data/benchmarks/ (small files committed to repo — works on Vercel/Render)
    2. local_data path on disk (dev machine)
    3. data/cache/ if already downloaded
    4. remote_data URL → download to cache
    """
    force = force or bool(config.get("force_refresh"))

    bundled_map = {
        "kaggle_uhi_csv": "urban_heat_island_dataset.csv",
        "ey_uhi_training_csv": "Training_data_uhi_index_2025-02-18.csv",
    }
    bundled_name = bundled_map.get(key)
    if bundled_name:
        bundled = BENCHMARKS_DIR / bundled_name
        if bundled.exists() and not force:
            return bundled

    local_raw = (config.get("local_data") or {}).get(key, "")
    if local_raw:
        local_path = Path(str(local_raw)).expanduser()
        if local_path.exists():
            return local_path

    remote: dict[str, Any] = (config.get("remote_data") or {}).get(key) or {}
    if not remote and not bundled_name:
        return None

    cache = _cache_root(config)
    filename = remote.get("filename") or bundled_name or f"{key}.bin"
    cache_path = cache / filename

    if cache_path.exists() and not force:
        return cache_path

    url = remote.get("url", "").strip()
    if not url:
        return bundled if bundled_name and (BENCHMARKS_DIR / bundled_name).exists() else None

    result = download_to_cache(
        url,
        cache_path,
        force=force,
        extract_zip=bool(remote.get("extract_zip")),
    )
    return result


def resolve_dataset_dir(config: dict, key: str, *, force: bool = False) -> Path | None:
    """Resolve a folder dataset (e.g. UTCI NetCDF directory)."""
    force = force or bool(config.get("force_refresh"))

    local_raw = (config.get("local_data") or {}).get(key, "")
    if local_raw:
        local_path = Path(str(local_raw)).expanduser()
        if local_path.is_dir():
            return local_path

    remote: dict[str, Any] = (config.get("remote_data") or {}).get(key) or {}
    cache = _cache_root(config)

    dir_name = remote.get("dirname") or key
    dir_path = cache / dir_name
    if dir_path.is_dir() and any(dir_path.iterdir()) and not force:
        return dir_path

    zip_file = remote.get("zip_filename") or f"{key}.zip"
    zip_path = cache / zip_file
    url = remote.get("url", "").strip()
    if not url:
        return None

    extracted = download_to_cache(url, zip_path, force=force, extract_zip=True)
    return extracted if extracted.is_dir() else dir_path
