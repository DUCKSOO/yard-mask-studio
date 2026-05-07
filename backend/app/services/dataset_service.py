"""데이터셋 생성·조회·타일 생성."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config_schema import LabelingConfig
from backend.app.core.db import DatasetConfigSnapshotRow, DatasetRow
from backend.app.core.config_store import load_active_config
from backend.app.tiling.coordinate_utils import gsd_cm_from_geotransform
from backend.app.tiling.raster_source import GeoTiffRasterSource
from backend.app.tiling.tile_generator import iter_tile_windows
from backend.app.tiling import tile_index


def create_dataset(
    session: Session,
    *,
    tenant_id: str,
    dataset_id: str,
    source_geotiff: str | None = None,
) -> DatasetRow:
    cfg = load_active_config(session)
    if cfg is None:
        raise RuntimeError("active_config missing; seed YAML first")
    now = datetime.now(UTC).isoformat()
    existing = session.scalars(
        select(DatasetRow).where(DatasetRow.tenant_id == tenant_id, DatasetRow.dataset_id == dataset_id)
    ).first()
    if existing is not None:
        raise ValueError("dataset already exists")

    snap = DatasetConfigSnapshotRow(
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        config_json=cfg.model_dump_json(),
        created_at=now,
    )
    session.add(snap)
    session.flush()
    row = DatasetRow(
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        config_snapshot_id=snap.id,
        source_geotiff=source_geotiff,
        created_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_dataset(session: Session, tenant_id: str, dataset_id: str) -> DatasetRow | None:
    return session.scalars(
        select(DatasetRow).where(DatasetRow.tenant_id == tenant_id, DatasetRow.dataset_id == dataset_id)
    ).first()


def list_datasets(session: Session, tenant_id: str) -> list[DatasetRow]:
    stmt = select(DatasetRow).where(DatasetRow.tenant_id == tenant_id).order_by(DatasetRow.created_at.desc())
    return list(session.scalars(stmt))


def get_dataset_labeling_config(session: Session, tenant_id: str, dataset_id: str) -> LabelingConfig:
    dr = get_dataset(session, tenant_id, dataset_id)
    if dr is None:
        raise KeyError("dataset not found")
    snap = session.get(DatasetConfigSnapshotRow, dr.config_snapshot_id)
    if snap is None:
        raise RuntimeError("snapshot missing")
    return LabelingConfig.model_validate_json(snap.config_json)


def raw_geotiff_path(repo_root: Path, tenant_id: str, filename: str) -> Path:
    return repo_root / "data" / "source" / tenant_id / "raw_geotiff" / filename


def dataset_dir(repo_root: Path, tenant_id: str, dataset_id: str) -> Path:
    return repo_root / "data" / "datasets" / tenant_id / dataset_id


def generate_tiles(
    session: Session,
    repo_root: Path,
    tenant_id: str,
    dataset_id: str,
    *,
    source_geotiff: str | None = None,
) -> int:
    dr = get_dataset(session, tenant_id, dataset_id)
    if dr is None:
        raise KeyError("dataset not found")
    fname = source_geotiff or dr.source_geotiff
    if not fname:
        raise ValueError("source_geotiff required")
    if source_geotiff:
        dr.source_geotiff = source_geotiff
        session.commit()

    tif_path = raw_geotiff_path(repo_root, tenant_id, fname)
    if not tif_path.is_file():
        raise FileNotFoundError(str(tif_path))

    cfg = get_dataset_labeling_config(session, tenant_id, dataset_id)
    images_dir = dataset_dir(repo_root, tenant_id, dataset_id) / "images"
    meta_dir = dataset_dir(repo_root, tenant_id, dataset_id) / "metadata"
    images_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    with GeoTiffRasterSource(tif_path) as src:
        gsd_x_cm, gsd_y_cm, gsd_src = gsd_cm_from_geotransform(src.transform, src.crs)
        tf = src.transform
        geo_transform = [float(tf.c), float(tf.a), float(tf.b), float(tf.f), float(tf.d), float(tf.e)]
        crs_str = src.crs.to_string() if src.crs else None
        band1_nd = src.nodata_for_band(1)
        nd_val = None if band1_nd is None else float(band1_nd)
        nodata_meta = {
            "has_nodata": band1_nd is not None,
            "value": nd_val,
            "source": "rasterio",
        }

        for tw in iter_tile_windows(src, cfg.tiling):
            tile_id = f"tile_{tw.row_off:06d}_{tw.col_off:06d}"
            png_path = images_dir / f"{tile_id}.png"
            arr = tw.data
            if arr.shape[0] >= 3:
                rgb = np.transpose(arr[:3], (1, 2, 0))
            else:
                band = arr[0]
                rgb = np.stack([band, band, band], axis=-1)
            if rgb.dtype != np.uint8:
                mx = float(rgb.max()) if rgb.size else 1.0
                if mx <= 1.0:
                    rgb = (rgb * 255.0).clip(0, 255)
                rgb = rgb.astype(np.uint8)
            Image.fromarray(rgb).save(png_path)

            meta = {
                "tile_id": tile_id,
                "tenant_id": tenant_id,
                "dataset_id": dataset_id,
                "tile_size": cfg.tiling.tile_size,
                "x": tw.col_off,
                "y": tw.row_off,
                "overlap": cfg.tiling.tile_overlap,
                "source_image": fname,
                "dataset_config_snapshot_id": dr.config_snapshot_id,
                "status": "unlabeled",
                "crs": crs_str,
                "geo_transform": geo_transform,
                "nodata": nodata_meta,
                "measured_gsd_x_cm": gsd_x_cm,
                "measured_gsd_y_cm": gsd_y_cm,
                "gsd_source": gsd_src,
                "expected_gsd_cm": cfg.geo.expected_gsd_cm,
                "manual_gsd_cm": cfg.geo.manual_gsd_cm,
                "mask_schema_version": cfg.classes.schema_version,
            }
            (meta_dir / f"{tile_id}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            tile_index.upsert_tile(
                session,
                tenant_id=tenant_id,
                dataset_id=dataset_id,
                tile_id=tile_id,
                status="unlabeled",
                metadata_json=json.dumps(meta),
            )
            count += 1
    return count
