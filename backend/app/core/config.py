"""LabelingConfig 로드: DB 우선, 없으면 YAML 시드."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.core.config_schema import LabelingConfig
from backend.app.core.config_store import load_active_config, seed_from_yaml
from backend.app.core.settings import Settings


def ensure_active_config(session: Session, settings: Settings, cwd: Path | None = None) -> LabelingConfig:
    existing = load_active_config(session)
    if existing is not None:
        return existing
    path = settings.resolved_labeling_config_path(cwd)
    if not path.is_file():
        raise FileNotFoundError(f"LABELING_CONFIG_PATH not found: {path}")
    return seed_from_yaml(session, path)
