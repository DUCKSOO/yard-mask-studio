"""타일 메타데이터 JSON 에 GSD·CRS·스냅샷 필드가 포함되는지 검증."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.config_store import seed_from_yaml
from backend.app.core.db import init_db
from backend.app.core.settings import clear_settings_cache
from backend.app.services import dataset_service
from backend.scripts.make_test_geotiff import write_synthetic_geotiff

MINIMAL_YAML = """
tiling:
  tile_size: 256
  tile_overlap: 64
  nodata_skip_threshold: 0.8
  edge_padding_strategy: "zero"
geo:
  expected_gsd_cm: 2.0
  gsd_tolerance: 0.5
  manual_gsd_cm: null
  default_crs: "EPSG:5186"
grid:
  size_meters: 15.0
  origin: "source_image_top_left"
sam:
  model_variant: "hiera_large"
  multimask_output: true
  max_candidates: 3
classes:
  schema_version: "1.0"
  definitions:
    - id: 0
      name: "non_occupied"
      color: "#000000"
    - id: 1
      name: "occupied"
      color: "#FF0000"
dataset:
  output_root: "data/exports"
  split_ratio:
    train: 0.7
    val: 0.15
    test: 0.15
  image_format: "png"
  mask_format: "png"
"""


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    raw = repo / "data" / "source" / "default" / "raw_geotiff"
    raw.mkdir(parents=True)
    write_synthetic_geotiff(raw / "t.tif", width=400, height=400, pixel_size_m=0.02)
    cfg_dir = repo / "config"
    cfg_dir.mkdir()
    (cfg_dir / "seed.yaml").write_text(MINIMAL_YAML.strip(), encoding="utf-8")
    return repo


def test_generate_tiles_metadata_includes_gsd_and_snapshot(tiny_repo: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tiny_repo)
    db_path = tiny_repo / "db.sqlite"
    url = f"sqlite:///{db_path.as_posix()}"
    clear_settings_cache()
    engine = create_engine(url, future=True)
    init_db(engine)
    with Session(engine) as session:
        seed_from_yaml(session, tiny_repo / "config" / "seed.yaml")
        dataset_service.create_dataset(
            session,
            tenant_id="default",
            dataset_id="d1",
            source_geotiff="t.tif",
        )
        n = dataset_service.generate_tiles(session, tiny_repo, "default", "d1")
    assert n >= 1

    meta_dir = tiny_repo / "data" / "datasets" / "default" / "d1" / "metadata"
    metas = sorted(meta_dir.glob("tile_*.json"))
    assert metas
    data = json.loads(metas[0].read_text(encoding="utf-8"))
    assert data["dataset_config_snapshot_id"] is not None
    assert data["gsd_source"] == "geotiff_transform"
    assert abs(float(data["measured_gsd_x_cm"]) - 2.0) < 1e-6
    assert abs(float(data["measured_gsd_y_cm"]) - 2.0) < 1e-6
    assert data["expected_gsd_cm"] == 2.0
    assert data["mask_schema_version"] == "1.0"
    assert data["crs"] == "EPSG:5186"
    assert len(data["geo_transform"]) == 6
    assert "nodata" in data
