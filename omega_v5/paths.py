#!/usr/bin/env python3
# ==============================================================================
# paths.py -- Canonical repository/runtime path helpers.
# ==============================================================================

from __future__ import annotations

import os
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent


def _resolve_under_root(value: str | os.PathLike[str]) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def repo_path(*parts: str) -> Path:
    return REPO_ROOT.joinpath(*parts)


def env_path() -> Path:
    return _resolve_under_root(os.environ.get("OMEGA_ENV_PATH", ".env"))


def output_dir() -> Path:
    return _resolve_under_root(os.environ.get("OMEGA_OUT_DIR", "out"))


def output_path(*parts: str) -> Path:
    return output_dir().joinpath(*parts)


def cache_dir() -> Path:
    return _resolve_under_root(os.environ.get("OMEGA_CACHE_DIR", "cache"))


def cache_path(*parts: str) -> Path:
    return cache_dir().joinpath(*parts)


def logs_dir() -> Path:
    return _resolve_under_root(os.environ.get("OMEGA_LOG_DIR", "logs"))


def logs_path(*parts: str) -> Path:
    return logs_dir().joinpath(*parts)


def notebooks_dir() -> Path:
    return repo_path("notebooks")


def notebook_path(name: str) -> Path:
    return notebooks_dir() / name


def indexer_compose_path() -> Path:
    return repo_path("infra", "compose", "docker-compose.indexer.yml")


def resolve_repo_relative(path: str | os.PathLike[str]) -> Path:
    return _resolve_under_root(path)
