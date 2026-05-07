"""active_config CRUD, 변경 스냅샷, YAML 시드."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config_schema import LabelingConfig
from backend.app.core.db import ActiveConfigRow, ConfigChangeSnapshotRow


def load_active_config(session: Session) -> LabelingConfig | None:
    row = session.get(ActiveConfigRow, 1)
    if row is None:
        return None
    return LabelingConfig.model_validate_json(row.config_json)


def seed_from_yaml(session: Session, path: Path) -> LabelingConfig:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cfg = LabelingConfig.from_yaml_mapping(raw)
    now = datetime.now(UTC).isoformat()
    session.merge(
        ActiveConfigRow(
            id=1,
            config_json=cfg.model_dump_json(),
            updated_at=now,
        )
    )
    session.commit()
    return cfg


def save_active_config(session: Session, new: LabelingConfig, reason: str = "user_edit") -> LabelingConfig:
    old = load_active_config(session)
    now = datetime.now(UTC).isoformat()
    if old is not None:
        session.add(
            ConfigChangeSnapshotRow(
                config_json=old.model_dump_json(),
                reason=reason,
                created_at=now,
            )
        )
    session.merge(
        ActiveConfigRow(
            id=1,
            config_json=new.model_dump_json(),
            updated_at=now,
        )
    )
    session.commit()
    return new


def list_config_snapshots(session: Session, limit: int = 100) -> list[ConfigChangeSnapshotRow]:
    stmt = select(ConfigChangeSnapshotRow).order_by(ConfigChangeSnapshotRow.id.desc()).limit(limit)
    return list(session.scalars(stmt))


def get_config_snapshot(session: Session, snapshot_id: int) -> ConfigChangeSnapshotRow | None:
    return session.get(ConfigChangeSnapshotRow, snapshot_id)


def rollback_to_snapshot(session: Session, snapshot_id: int) -> LabelingConfig:
    row = session.get(ConfigChangeSnapshotRow, snapshot_id)
    if row is None:
        raise ValueError(f"snapshot {snapshot_id} not found")
    cfg = LabelingConfig.model_validate_json(row.config_json)
    return save_active_config(session, cfg, reason="rollback")
