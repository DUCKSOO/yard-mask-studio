"""SQLite 타일 인덱스 CRUD."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.db import TileRow


def upsert_tile(
    session: Session,
    *,
    tenant_id: str,
    dataset_id: str,
    tile_id: str,
    status: str = "unlabeled",
    metadata_json: str | None = None,
) -> TileRow:
    now = datetime.now(UTC).isoformat()
    stmt = select(TileRow).where(
        TileRow.tenant_id == tenant_id,
        TileRow.dataset_id == dataset_id,
        TileRow.tile_id == tile_id,
    )
    row = session.scalars(stmt).first()
    if row is None:
        row = TileRow(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            tile_id=tile_id,
            status=status,
            metadata_json=metadata_json,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.status = status
        if metadata_json is not None:
            row.metadata_json = metadata_json
        row.updated_at = now
    session.commit()
    session.refresh(row)
    return row


def list_tiles(
    session: Session,
    tenant_id: str,
    dataset_id: str,
    *,
    status: str | None = None,
    limit: int = 20,
) -> list[TileRow]:
    stmt = select(TileRow).where(TileRow.tenant_id == tenant_id, TileRow.dataset_id == dataset_id)
    if status is not None:
        stmt = stmt.where(TileRow.status == status)
    stmt = stmt.order_by(TileRow.tile_id).limit(limit)
    return list(session.scalars(stmt))


def get_tile(session: Session, tenant_id: str, dataset_id: str, tile_id: str) -> TileRow | None:
    stmt = select(TileRow).where(
        TileRow.tenant_id == tenant_id,
        TileRow.dataset_id == dataset_id,
        TileRow.tile_id == tile_id,
    )
    return session.scalars(stmt).first()


def update_tile_status(session: Session, tenant_id: str, dataset_id: str, tile_id: str, status: str) -> TileRow | None:
    row = get_tile(session, tenant_id, dataset_id, tile_id)
    if row is None:
        return None
    row.status = status
    row.updated_at = datetime.now(UTC).isoformat()
    session.commit()
    session.refresh(row)
    return row
