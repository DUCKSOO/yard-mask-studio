"""U-Net 학습용 데이터셋 export — 라벨된 타일만 복사·분할·검증."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.db import AnnotationRow, ExportRow
from backend.app.dataset.split_generator import assign_splits, write_split_files
from backend.app.dataset.validator import validate_export
from backend.app.services import dataset_service


def export_dir_for(repo_root: Path, tenant_id: str, dataset_id: str, export_id: str) -> Path:
    return repo_root / "data" / "exports" / tenant_id / dataset_id / export_id


def export_unet_dataset(
    session: Session,
    repo_root: Path,
    tenant_id: str,
    dataset_id: str,
    *,
    split_seed: int | None = None,
) -> str:
    """라벨된 annotation + 디스크상 image/mask가 있는 타일만 export. export UUID를 반환."""
    repo_root = repo_root.resolve()
    dr = dataset_service.get_dataset(session, tenant_id, dataset_id)
    if dr is None:
        raise KeyError("dataset not found")

    cfg = dataset_service.get_dataset_labeling_config(session, tenant_id, dataset_id)
    ddir = dataset_service.dataset_dir(repo_root, tenant_id, dataset_id)

    stmt = select(AnnotationRow).where(
        AnnotationRow.tenant_id == tenant_id,
        AnnotationRow.dataset_id == dataset_id,
    )
    rows = list(session.scalars(stmt))

    labeled_tile_ids: list[str] = []
    for row in rows:
        try:
            payload = json.loads(row.annotation_json)
        except json.JSONDecodeError:
            continue
        if payload.get("status") != "labeled":
            continue
        tile_id = row.tile_id
        img_p = ddir / "images" / f"{tile_id}.png"
        mask_p = ddir / "masks" / f"{tile_id}.png"
        if not img_p.is_file() or not mask_p.is_file():
            continue
        labeled_tile_ids.append(tile_id)

    if not labeled_tile_ids:
        raise ValueError("no labeled tiles with image and mask on disk to export")

    export_id = str(uuid.uuid4())
    out = export_dir_for(repo_root, tenant_id, dataset_id, export_id)
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    (out / "masks").mkdir(parents=True)

    for tile_id in labeled_tile_ids:
        shutil.copy2(ddir / "images" / f"{tile_id}.png", out / "images" / f"{tile_id}.png")
        # 마스크는 클래스 인덱스(0/1/2…)로 저장돼 있어 시각적으로 검정처럼 보임.
        # 내보내기 시 occupied(>0) → 255, background(0) → 0 으로 바이너리 리맵.
        raw_mask = np.array(Image.open(ddir / "masks" / f"{tile_id}.png"))
        binary_mask = (raw_mask > 0).astype(np.uint8) * 255
        Image.fromarray(binary_mask, mode="L").save(out / "masks" / f"{tile_id}.png")

    (out / "classes.json").write_text(
        json.dumps(cfg.classes.model_dump(), indent=2),
        encoding="utf-8",
    )

    (out / "config_snapshot.yaml").write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    splits = assign_splits(labeled_tile_ids, cfg.dataset.split_ratio, seed=split_seed)
    write_split_files(out, splits)

    measured_x = float(cfg.geo.expected_gsd_cm)
    measured_y = float(cfg.geo.expected_gsd_cm)
    gsd_src = "expected"
    meta_path = ddir / "metadata" / f"{labeled_tile_ids[0]}.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if "measured_gsd_x_cm" in meta:
                measured_x = float(meta["measured_gsd_x_cm"])
            if "measured_gsd_y_cm" in meta:
                measured_y = float(meta["measured_gsd_y_cm"])
            if isinstance(meta.get("gsd_source"), str):
                gsd_src = meta["gsd_source"]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    gw, gh = cfg.grid.to_pixels(measured_x, measured_y)

    manifest = {
        "dataset_id": dataset_id,
        "tenant_id": tenant_id,
        "export_id": export_id,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "tile_size": cfg.tiling.tile_size,
        "tile_overlap": cfg.tiling.tile_overlap,
        "expected_gsd_cm": cfg.geo.expected_gsd_cm,
        "measured_gsd_x_cm": measured_x,
        "measured_gsd_y_cm": measured_y,
        "manual_gsd_cm": cfg.geo.manual_gsd_cm,
        "gsd_source": gsd_src,
        "georeferencing": "full",
        "grid_size_meters": cfg.grid.size_meters,
        "grid_size_pixels_x": gw,
        "grid_size_pixels_y": gh,
        "mask_schema_version": cfg.classes.schema_version,
        "sample_count": len(labeled_tile_ids),
        "dataset_config_snapshot_id": dr.config_snapshot_id,
        "config_snapshot_path": "config_snapshot.yaml",
    }
    (out / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    verrors = validate_export(out)
    if verrors:
        shutil.rmtree(out)
        raise RuntimeError("export validation failed: " + "; ".join(verrors))

    now = datetime.now(UTC).isoformat()
    rel = out.relative_to(repo_root).as_posix()
    er = ExportRow(
        id=export_id,
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        status="done",
        export_path=rel,
        sample_count=len(labeled_tile_ids),
        created_at=now,
        error_detail=None,
    )
    session.add(er)
    session.commit()

    return export_id


def get_export(session: Session, tenant_id: str, export_id: str) -> ExportRow | None:
    row = session.get(ExportRow, export_id)
    if row is None or row.tenant_id != tenant_id:
        return None
    return row
