"""dataset_exporter 통합(임시 레포 + SQLite)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from backend.app.core.config_store import seed_from_yaml
from backend.app.core.db import AnnotationRow, ExportRow
from backend.app.dataset.dataset_exporter import export_unet_dataset, get_export
from backend.app.dataset.validator import validate_export
from backend.app.services import dataset_service

_REPO = Path(__file__).resolve().parents[2]


def _write_tile_pair(ddir: Path, tile_id: str, size: int = 8) -> None:
    (ddir / "images").mkdir(parents=True, exist_ok=True)
    (ddir / "masks").mkdir(parents=True, exist_ok=True)
    rgb = np.random.randint(0, 255, (size, size, 3), dtype=np.uint8)
    Image.fromarray(rgb, mode="RGB").save(ddir / "images" / f"{tile_id}.png")
    mask = np.zeros((size, size), dtype=np.uint8)
    mask[0, 0] = 1
    mask[1, 1] = 255
    Image.fromarray(mask, mode="L").save(ddir / "masks" / f"{tile_id}.png")


def test_export_unet_roundtrip(db_session: Session, tmp_path: Path) -> None:
    seed_from_yaml(db_session, _REPO / "config" / "labeling.dev.yaml")
    dataset_service.create_dataset(
        db_session,
        tenant_id="default",
        dataset_id="ds_export_test",
        source_geotiff=None,
    )
    rr = tmp_path.resolve()
    ddir = dataset_service.dataset_dir(rr, "default", "ds_export_test")
    _write_tile_pair(ddir, "tile_a")

    now = datetime.now(UTC).isoformat()
    ann = AnnotationRow(
        tenant_id="default",
        dataset_id="ds_export_test",
        tile_id="tile_a",
        annotation_json=json.dumps(
            {
                "status": "labeled",
                "mask_encoding": "rle",
                "class_mask": {"height": 8, "width": 8, "counts": "0:64"},
            }
        ),
        updated_at=now,
    )
    db_session.add(ann)
    db_session.commit()

    eid = export_unet_dataset(db_session, rr, "default", "ds_export_test", split_seed=42)
    assert len(eid) == 36

    row = get_export(db_session, "default", eid)
    assert row is not None
    assert row.sample_count == 1
    assert row.status == "done"

    out = rr / row.export_path
    assert out.is_dir()
    assert validate_export(out) == []
    assert (out / "dataset_manifest.json").is_file()
    assert (out / "config_snapshot.yaml").is_file()


def test_export_no_labeled_raises(db_session: Session, tmp_path: Path) -> None:
    seed_from_yaml(db_session, _REPO / "config" / "labeling.dev.yaml")
    dataset_service.create_dataset(db_session, tenant_id="default", dataset_id="ds_empty", source_geotiff=None)
    rr = tmp_path.resolve()
    ddir = dataset_service.dataset_dir(rr, "default", "ds_empty")
    _write_tile_pair(ddir, "tile_x")
    db_session.commit()

    try:
        export_unet_dataset(db_session, rr, "default", "ds_empty")
    except ValueError as e:
        assert "no labeled" in str(e).lower()
    else:
        raise AssertionError("expected ValueError")
