"""API 요청/응답 모델 — docs/api_spec.yaml 정합."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.core.config_schema import LabelingConfig


class DatasetCreateRequest(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=128)
    source_geotiff: str | None = None


class TileGenerateRequest(BaseModel):
    source_geotiff: str | None = None


class SamPointPromptIn(BaseModel):
    type: Literal["point"] = "point"
    x: int
    y: int
    label: Literal["positive", "negative"] = "positive"


class SamBoxPromptIn(BaseModel):
    type: Literal["box"] = "box"
    x1: int
    y1: int
    x2: int
    y2: int


class SamPredictRequest(BaseModel):
    prompts: list[dict[str, Any]] = Field(default_factory=list)
    multimask_output: bool | None = None


class ClassMaskRLE(BaseModel):
    height: int
    width: int
    counts: str


class AnnotationSaveRequest(BaseModel):
    status: str = "labeled"
    mask_encoding: Literal["rle"] = "rle"
    class_mask: ClassMaskRLE


class TileStatusPatch(BaseModel):
    status: str
