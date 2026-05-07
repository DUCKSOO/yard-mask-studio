"""LabelingConfig · YAML 시드 정합 테스트."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from backend.app.core.config_schema import GridConfig, LabelingConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_YAML = REPO_ROOT / "config" / "labeling.dev.yaml"


def _load_dev_mapping() -> dict:
    with DEV_YAML.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    return data


def test_labeling_dev_yaml_parses() -> None:
    raw = _load_dev_mapping()
    cfg = LabelingConfig.from_yaml_mapping(raw)
    assert cfg.tiling.tile_size == 1024
    assert cfg.sam.model_variant == "hiera_large"
    assert cfg.classes.definitions[2].id == 255


def test_labeling_prod_yaml_parses() -> None:
    path = REPO_ROOT / "config" / "labeling.prod.yaml"
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    cfg = LabelingConfig.from_yaml_mapping(data)
    assert cfg.dataset.output_root == "data/exports_prod"


def test_grid_to_pixels_15m_at_2cm_gsd() -> None:
    g = GridConfig(size_meters=15.0, origin="source_image_top_left")
    assert g.to_pixels(2.0, 2.0) == (750, 750)


def test_tile_overlap_must_be_less_than_tile_size() -> None:
    raw = _load_dev_mapping()
    raw["tiling"]["tile_overlap"] = raw["tiling"]["tile_size"]
    with pytest.raises(ValidationError):
        LabelingConfig.from_yaml_mapping(raw)


def test_split_ratio_must_sum_to_one() -> None:
    raw = _load_dev_mapping()
    raw["dataset"]["split_ratio"]["train"] = 0.5
    with pytest.raises(ValidationError):
        LabelingConfig.from_yaml_mapping(raw)


def test_invalid_grid_origin() -> None:
    raw = _load_dev_mapping()
    raw["grid"]["origin"] = "invalid"
    with pytest.raises(ValidationError):
        LabelingConfig.from_yaml_mapping(raw)


def test_invalid_edge_padding_strategy() -> None:
    raw = _load_dev_mapping()
    raw["tiling"]["edge_padding_strategy"] = "mirror"
    with pytest.raises(ValidationError):
        LabelingConfig.from_yaml_mapping(raw)


def test_invalid_sam_model_variant() -> None:
    raw = _load_dev_mapping()
    raw["sam"]["model_variant"] = "hiera_tiny"
    with pytest.raises(ValidationError):
        LabelingConfig.from_yaml_mapping(raw)


def test_duplicate_class_ids_rejected() -> None:
    raw = _load_dev_mapping()
    defs = deepcopy(raw["classes"]["definitions"])
    defs.append({"id": 1, "name": "dup", "color": "#00FF00"})
    raw["classes"]["definitions"] = defs
    with pytest.raises(ValidationError):
        LabelingConfig.from_yaml_mapping(raw)


def test_manual_gsd_must_be_positive_when_set() -> None:
    raw = _load_dev_mapping()
    raw["geo"]["manual_gsd_cm"] = -1.0
    with pytest.raises(ValidationError):
        LabelingConfig.from_yaml_mapping(raw)
