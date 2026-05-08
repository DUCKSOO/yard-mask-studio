"""API 스모크 — TestClient."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.config_store import seed_from_yaml
from backend.app.core.db import AnnotationRow, ExportRow, init_db
from backend.app.dataset.dataset_exporter import export_unet_dataset
from backend.app.services import dataset_service

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_get_config(api_client) -> None:
    r = api_client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["tiling"]["tile_size"] == 1024


def test_create_dataset_and_list(api_client) -> None:
    r = api_client.post(
        "/api/tenants/default/datasets",
        json={"dataset_id": "ds_test", "source_geotiff": None},
    )
    assert r.status_code == 201
    r2 = api_client.get("/api/tenants/default/datasets")
    assert r2.status_code == 200
    ids = [x["dataset_id"] for x in r2.json()]
    assert "ds_test" in ids


def test_export_missing_dataset_404(api_client) -> None:
    r = api_client.post("/api/tenants/default/datasets/no_such_ds/export/unet")
    assert r.status_code == 404


def test_export_no_labels_400(api_client) -> None:
    uid = f"ds_export_api_{uuid.uuid4().hex[:8]}"
    r = api_client.post(
        "/api/tenants/default/datasets",
        json={"dataset_id": uid, "source_geotiff": None},
    )
    assert r.status_code == 201
    r2 = api_client.post(f"/api/tenants/default/datasets/{uid}/export/unet")
    assert r2.status_code == 400


def test_export_status_unknown_404(api_client) -> None:
    r = api_client.get(f"/api/tenants/default/exports/{uuid.uuid4()}/status")
    assert r.status_code == 404


def test_export_download_unknown_404(api_client) -> None:
    r = api_client.get(f"/api/tenants/default/exports/{uuid.uuid4()}/download")
    assert r.status_code == 404


def test_unet_dataloader_smoke_script_runs_on_sample_export(tmp_path: Path) -> None:
    """dataset_exporter로 만든 export에 대해 스크립트 1회 실행."""
    db_path = tmp_path / "smoke.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    init_db(engine)
    rr = tmp_path.resolve()
    with Session(engine) as session:
        seed_from_yaml(session, REPO_ROOT / "config" / "labeling.dev.yaml")
        dataset_service.create_dataset(session, tenant_id="default", dataset_id="ds_smoke", source_geotiff=None)
        ddir = dataset_service.dataset_dir(rr, "default", "ds_smoke")
        (ddir / "images").mkdir(parents=True, exist_ok=True)
        (ddir / "masks").mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8), "RGB").save(ddir / "images" / "tile_a.png")
        m = np.zeros((8, 8), dtype=np.uint8)
        m[0, 0] = 1
        m[1, 1] = 255
        Image.fromarray(m, mode="L").save(ddir / "masks" / "tile_a.png")
        now = datetime.now(UTC).isoformat()
        session.add(
            AnnotationRow(
                tenant_id="default",
                dataset_id="ds_smoke",
                tile_id="tile_a",
                annotation_json=json.dumps({"status": "labeled", "mask_encoding": "rle", "class_mask": {}}),
                updated_at=now,
            )
        )
        session.commit()
        out_id = export_unet_dataset(session, rr, "default", "ds_smoke", split_seed=0)
        er = session.get(ExportRow, out_id)
        assert er is not None
        export_path = rr / er.export_path

    script = REPO_ROOT / "backend" / "scripts" / "unet_dataloader_smoke.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(export_path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
