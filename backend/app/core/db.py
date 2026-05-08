"""SQLite + SQLAlchemy 2.0 동기 엔진 및 ORM 모델."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class ActiveConfigRow(Base):
    __tablename__ = "active_config"
    __table_args__ = (CheckConstraint("id = 1", name="ck_active_config_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class ConfigChangeSnapshotRow(Base):
    __tablename__ = "config_change_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class DatasetConfigSnapshotRow(Base):
    __tablename__ = "dataset_config_snapshots"
    __table_args__ = (UniqueConstraint("tenant_id", "dataset_id", name="uq_dataset_snapshot_tenant_dataset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class DatasetRow(Base):
    """데이터셋 레지스트리 (스냅샷 id 참조)."""

    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("tenant_id", "dataset_id", name="uq_datasets_tenant_dataset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    config_snapshot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_geotiff: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class TileRow(Base):
    __tablename__ = "tiles"
    __table_args__ = (UniqueConstraint("tenant_id", "dataset_id", "tile_id", name="uq_tiles_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    tile_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="unlabeled")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class AnnotationRow(Base):
    __tablename__ = "annotations"
    __table_args__ = (UniqueConstraint("tenant_id", "dataset_id", "tile_id", name="uq_annotations_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    tile_id: Mapped[str] = mapped_column(Text, nullable=False)
    annotation_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class ExportRow(Base):
    """U-Net export 작업 레지스트리."""

    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    export_path: Mapped[str] = mapped_column(Text, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReviewQueueRow(Base):
    """타일 검수 큐 (타일당 최대 1행)."""

    __tablename__ = "review_queue"
    __table_args__ = (UniqueConstraint("tenant_id", "dataset_id", "tile_id", name="uq_review_queue_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    tile_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


def init_db(engine) -> None:
    Base.metadata.create_all(bind=engine)


def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
