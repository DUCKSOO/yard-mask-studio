"""검수 큐 DB upsert — annotation 저장과 review API에서 공통 사용."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.db import ReviewQueueRow


def upsert_review_row(
    db: Session,
    *,
    tenant_id: str,
    dataset_id: str,
    tile_id: str,
    status: str,
    note: str | None = None,
) -> ReviewQueueRow:
    now = datetime.now(UTC).isoformat()
    stmt = select(ReviewQueueRow).where(
        ReviewQueueRow.tenant_id == tenant_id,
        ReviewQueueRow.dataset_id == dataset_id,
        ReviewQueueRow.tile_id == tile_id,
    )
    row = db.scalars(stmt).first()
    if row is None:
        row = ReviewQueueRow(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            tile_id=tile_id,
            status=status,
            note=note,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.status = status
        row.note = note
        row.updated_at = now
    return row


def delete_review_row(
    db: Session,
    *,
    tenant_id: str,
    dataset_id: str,
    tile_id: str,
) -> None:
    stmt = select(ReviewQueueRow).where(
        ReviewQueueRow.tenant_id == tenant_id,
        ReviewQueueRow.dataset_id == dataset_id,
        ReviewQueueRow.tile_id == tile_id,
    )
    row = db.scalars(stmt).first()
    if row is not None:
        db.delete(row)
