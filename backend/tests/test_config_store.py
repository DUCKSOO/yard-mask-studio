"""config_store 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.core.config_schema import LabelingConfig
from backend.app.core.config_store import (
    load_active_config,
    save_active_config,
    seed_from_yaml,
)
_REPO = Path(__file__).resolve().parents[2]


def test_seed_from_yaml_empty_db(db_session: Session) -> None:
    cfg = seed_from_yaml(db_session, _REPO / "config" / "labeling.dev.yaml")
    assert isinstance(cfg, LabelingConfig)
    again = load_active_config(db_session)
    assert again is not None
    assert again.tiling.tile_size == cfg.tiling.tile_size


def test_save_active_creates_snapshot(db_session: Session) -> None:
    seed_from_yaml(db_session, _REPO / "config" / "labeling.dev.yaml")
    cfg = load_active_config(db_session)
    assert cfg is not None
    new = cfg.model_copy(deep=True)
    new.tiling.tile_size = 512
    save_active_config(db_session, new)
    from sqlalchemy import func, select

    from backend.app.core.db import ConfigChangeSnapshotRow

    n = db_session.scalar(select(func.count(ConfigChangeSnapshotRow.id)))
    assert n == 1
