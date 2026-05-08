"""API 요청/응답 모델 — docs/api_spec.yaml 정합."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.core.config_schema import LabelingConfig


class DatasetCreateRequest(BaseModel):
    dataset_id: str = Field(
        min_length=1,
        max_length=128,
        description="새 데이터셋의 고유 ID(테넌트 내). 이후 경로 `/datasets/{dataset_id}`에 사용.",
        examples=["my_yard_v1"],
    )
    source_geotiff: str | None = Field(
        default=None,
        description="원본 GeoTIFF **파일명만**. 실제 경로는 `data/source/{tenant_id}/raw_geotiff/{파일명}`. 타일 생성 전까지 생략 가능.",
        examples=["(B060)정사영상_2025_34602097.tif"],
    )


class TileGenerateRequest(BaseModel):
    source_geotiff: str | None = Field(
        default=None,
        description="이번 생성에만 쓸 원본 파일명. 생략 시 데이터셋에 저장된 `source_geotiff` 사용.",
        examples=["synthetic_step3.tif"],
    )


class SamPointPromptIn(BaseModel):
    type: Literal["point"] = "point"
    x: int = Field(description="타일 이미지 기준 픽셀 x (0 ~ width-1).")
    y: int = Field(description="타일 이미지 기준 픽셀 y (0 ~ height-1).")
    label: Literal["positive", "negative"] = Field(
        default="positive",
        description="전경(양성) 또는 배경(음성) 프롬프트.",
    )


class SamBoxPromptIn(BaseModel):
    type: Literal["box"] = "box"
    x1: int = Field(description="박스 좌상단 x (픽셀).")
    y1: int = Field(description="박스 좌상단 y (픽셀).")
    x2: int = Field(description="박스 우하단 x (픽셀).")
    y2: int = Field(description="박스 우하단 y (픽셀).")


class SamPredictRequest(BaseModel):
    prompts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="SAM 프롬프트 배열. 요소는 `{\"type\":\"point\",\"x\", \"y\", \"label\"}` 또는 `{\"type\":\"box\",\"x1\",\"y1\",\"x2\",\"y2\"}` 형태.",
        examples=[[{"type": "point", "x": 256, "y": 256, "label": "positive"}]],
    )
    multimask_output: bool | None = Field(
        default=None,
        description="다중 마스크 후보 여부. 생략 시 서버/모델 기본값.",
    )


class ClassMaskRLE(BaseModel):
    height: int = Field(description="마스크 높이(px). 타일 PNG와 동일해야 함.")
    width: int = Field(description="마스크 너비(px). 타일 PNG와 동일해야 함.")
    counts: str = Field(
        description="행 우선(C-order) value:length RLE. 예: `0:100,1:50` 형태(쉼표로 구간 연결).",
        examples=["0:262144"],
    )


class AnnotationSaveRequest(BaseModel):
    status: str = Field(
        default="labeled",
        description="저장 후 타일에 반영할 상태. 예: `labeled`, `in_progress`.",
        examples=["labeled"],
    )
    mask_encoding: Literal["rle"] = Field(
        default="rle",
        description="마스크 인코딩. 현재는 `rle`만 지원.",
    )
    class_mask: ClassMaskRLE = Field(description="클래스 인덱스 마스크 RLE.")


class TileStatusPatch(BaseModel):
    status: str = Field(
        description="바꿀 타일 상태. 예: `unlabeled`, `in_progress`, `labeled`, `skipped` 등.",
        examples=["labeled"],
    )


class ExportUnetResponse(BaseModel):
    export_id: str = Field(description="생성된 export 작업 UUID. `GET .../exports/{export_id}/status`에 사용.")


class ExportStatusResponse(BaseModel):
    status: str = Field(description="작업 상태. MVP는 완료 시 `done`만 사용.")
    export_path: str = Field(description="레포 루트 기준 상대 경로(`data/exports/...`).")
    sample_count: int = Field(description="export에 포함된 타일(샘플) 수.")
    dataset_id: str = Field(description="원본 데이터셋 ID.")
    tenant_id: str = Field(description="테넌트 ID.")


class ReviewRejectBody(BaseModel):
    note: str | None = Field(default=None, description="거부 사유(선택).")


class ReviewQueueItem(BaseModel):
    tile_id: str
    dataset_id: str
    status: str
    note: str | None
    created_at: str


class ConfigImpactRequest(BaseModel):
    tile_size: int | None = Field(
        default=None,
        ge=1,
        description="가정할 tile_size(px). 생략 시 활성 설정의 값.",
    )
    tile_overlap: int | None = Field(
        default=None,
        ge=0,
        description="가정할 tile_overlap(px). 생략 시 활성 설정의 값.",
    )


class DatasetImpactItem(BaseModel):
    dataset_id: str = Field(description="데이터셋 ID.")
    tile_count: int = Field(description="해당 데이터셋의 현재 타일 수.")
    simulated_tile_count: int = Field(description="가정한 stride 비율로 추정한 타일 수.")


class ConfigImpactResponse(BaseModel):
    current_tile_count: int
    simulated_tile_count: int
    delta: int
    affected_datasets: list[DatasetImpactItem]
