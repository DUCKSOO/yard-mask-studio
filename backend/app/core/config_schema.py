"""Labeling 설정 Pydantic 스키마 — YAML 시드·DB active_config·API 본문 검증에 공통 사용.

새 SAM 모델 variant 추가 절차:
1. 체크포인트를 models/ 에 두고 .env 의 SAM_CHECKPOINT_PATH 를 맞춘다.
2. 아래 SamModelVariant Literal 과 SamConfig.model_variant 에 값을 추가한다.
3. config/labeling.dev.yaml (및 prod) 의 sam.model_variant 허용값을 문서화한다.
4. docs/api_spec.yaml 의 SamModelVariant enum 과 README 의 「SAM 모델 추가 방법」을 동기화한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# 허용 SAM 백본 variant (설계서 v0.3 기본). 추가 시 위 모듈 독스트링 절차를 따른다.
SamModelVariant = Literal["hiera_large", "hiera_base"]

EdgePaddingStrategy = Literal["zero", "reflect", "drop"]
GridOrigin = Literal["source_image_top_left", "geo_origin", "tile_top_left"]


class TilingConfig(BaseModel):
    tile_size: int = Field(default=1024, ge=128, le=4096)
    tile_overlap: int = Field(default=128, ge=0)
    nodata_skip_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    edge_padding_strategy: EdgePaddingStrategy = "zero"

    @model_validator(mode="after")
    def overlap_smaller_than_tile(self) -> TilingConfig:
        if self.tile_overlap >= self.tile_size:
            raise ValueError("tile_overlap must be smaller than tile_size")
        return self


class GeoConfig(BaseModel):
    expected_gsd_cm: float = Field(default=2.0, gt=0)
    gsd_tolerance: float = Field(default=0.5, ge=0)
    manual_gsd_cm: float | None = Field(default=None)
    default_crs: str = Field(default="EPSG:5186", min_length=1)

    @model_validator(mode="after")
    def manual_gsd_positive_when_set(self) -> GeoConfig:
        if self.manual_gsd_cm is not None and self.manual_gsd_cm <= 0:
            raise ValueError("manual_gsd_cm must be positive when set")
        return self


class GridConfig(BaseModel):
    size_meters: float = Field(default=15.0, gt=0)
    origin: GridOrigin = "source_image_top_left"

    def to_pixels(self, gsd_x_cm: float, gsd_y_cm: float) -> tuple[int, int]:
        """그리드 한 변의 픽셀 크기 (floor). 정책 변경 시 dataset / grid 스펙 버전을 올릴 것."""
        px_x = int(self.size_meters * 100 / gsd_x_cm)
        px_y = int(self.size_meters * 100 / gsd_y_cm)
        return (px_x, px_y)


class SamConfig(BaseModel):
    # 새 variant 추가: SamModelVariant · 아래 필드 · YAML · OpenAPI enum · README 동시 갱신.
    model_variant: SamModelVariant = "hiera_base"
    multimask_output: bool = True
    max_candidates: int = Field(default=3, ge=1, le=16)


class MaskClassDefinition(BaseModel):
    id: int = Field(ge=0, le=255)
    name: str = Field(min_length=1)
    color: str = Field(min_length=1, pattern=r"^#[0-9A-Fa-f]{6}$")


class ClassesConfig(BaseModel):
    schema_version: str = Field(default="1.0", min_length=1)
    definitions: list[MaskClassDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_class_ids(self) -> ClassesConfig:
        ids = [d.id for d in self.definitions]
        if len(ids) != len(set(ids)):
            raise ValueError("class definition ids must be unique")
        return self


class SplitRatio(BaseModel):
    train: float = Field(ge=0.0, le=1.0)
    val: float = Field(ge=0.0, le=1.0)
    test: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def sums_to_one(self) -> SplitRatio:
        total = self.train + self.val + self.test
        if abs(total - 1.0) > 1e-6:
            raise ValueError("split_ratio train + val + test must sum to 1.0 (within 1e-6)")
        return self


class DatasetConfig(BaseModel):
    output_root: str = Field(default="data/exports", min_length=1)
    split_ratio: SplitRatio
    image_format: Literal["png"] = "png"
    mask_format: Literal["png"] = "png"


class LabelingConfig(BaseModel):
    tiling: TilingConfig
    geo: GeoConfig
    grid: GridConfig
    sam: SamConfig
    classes: ClassesConfig
    dataset: DatasetConfig

    @classmethod
    def from_yaml_mapping(cls, data: object) -> LabelingConfig:
        if not isinstance(data, dict):
            raise TypeError("YAML root must be a mapping")
        return cls.model_validate(data)
