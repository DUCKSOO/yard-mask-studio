# 데이터셋 명세 (dataset_spec)

본 문서는 [labeling-tool-plan-v3.md](../labeling-tool-plan-v3.md) §2.4·§6을 구현·검증할 때의 단일 기준이다.

---

## 1. 저장소 경로 역할

| 경로 | 용도 |
|------|------|
| `data/source/{tenant_id}/raw_geotiff/` | 원본 GeoTIFF (입력) |
| `data/datasets/{tenant_id}/{dataset_id}/` | 라벨링 작업 산출: 타일 이미지·mask·메타데이터·스냅샷 |
| `data/exports/{tenant_id}/{dataset_id}/{export_id}/` | U-Net 학습용 최종 export (split·검증·포맷 변환 후) |

`datasets`는 라벨러가 편집하는 원본 작업 공간이고, `exports`는 학습 파이프라인에 넘기는 결과물이다. 둘 다 `{tenant_id}/{dataset_id}` 계층으로 격리한다.

---

## 2. 데이터셋 디렉터리 레이아웃 (`data/datasets/...`)

```
{tenant_id}/{dataset_id}/
  images/
    tile_000001.png
    tile_000002.png
  masks/
    tile_000001.png
    tile_000002.png
  metadata/
    tile_000001.json
    tile_000002.json
  splits/
    train.json
    val.json
    test.json
  config_snapshot.yaml    # 데이터셋 생성 시점 불변 설정
  classes.json
  dataset_manifest.json
```

---

## 3. mask PNG 규칙 (§6.2)

- 원본 타일 이미지와 **동일한 width/height**.
- **8-bit grayscale** PNG.
- 픽셀 값 = **클래스 ID** (정수 0–255). 컬러 팔레트 PNG·RGB mask 저장 **금지** (학습용은 class index만).
- 기본 클래스: `0` non_occupied, `1` occupied, `255` ignore (`classes.schema_version`에 따름).

---

## 4. 타일 메타데이터 JSON (`metadata/tile_*.json`) (§6.3)

필드 예시 (실제 키는 구현 시 동일 스키마로 직렬화):

| 필드 | 설명 |
|------|------|
| `tile_id` | 데이터셋 내 유일 ID (예: `tile_000001`) |
| `tenant_id` | 테넌트 |
| `source_image` | 원본 래스터 파일명 |
| `tile_size`, `x`, `y`, `overlap` | 타일 크기·원본 상의 좌상단 오프셋·overlap |
| `crs` | 좌표계 (예: EPSG:5186) |
| `geo_transform` | GDAL GeoTransform 6원소 `[origin_x, pixel_width, row_rotation, origin_y, column_rotation, pixel_height]` |
| `nodata` | `has_nodata`, `value`, `source` — rasterio/GDAL 메타 기준, 임의 추정 금지 |
| `measured_gsd_x_cm`, `measured_gsd_y_cm` | GeoTransform 기반 측정 GSD (cm/px) |
| `gsd_source` | 예: `geotiff_transform`, `manual`, `warning_needs_manual` |
| `expected_gsd_cm` | 설정 기준값 (검증·경고용) |
| `dataset_id`, `dataset_config_snapshot_id` | 데이터셋·불변 설정 스냅샷 참조 |
| `status` | §5 타일 상태 |
| `mask_schema_version` | 클래스 스키마 버전 |
| `created_at`, `updated_at`, `created_by`, `reviewed_by` | 감사 |
| `sam_model_version`, `sam_prompts` | SAM 사용 이력 (선택) |

**GSD (투영 CRS, 미터 단위):** `pixel_width_m * 100` → cm/px. `measured_gsd_x_cm` / `measured_gsd_y_cm`로 분리 저장.

**위경도 CRS 또는 rotation이 있는 GeoTransform:** 단순 환산 불가 시 경고·`gsd_source: warning_needs_manual` 등으로 표시.

---

## 5. 타일 상태 및 전이 (§6.4)

| 상태 | 의미 | 다음 가능 상태 |
|------|------|----------------|
| unlabeled | 작업 전 | in_progress, skipped |
| in_progress | 작업 중 | labeled, skipped |
| labeled | 1차 라벨 완료 | review_needed, approved |
| review_needed | 검수 필요 | approved, rejected |
| rejected | 재작업 필요 | in_progress |
| approved | 검수 완료 | (최종) |
| skipped | 라벨링 제외 | (최종) |

---

## 6. `dataset_manifest.json` (§2.4)

데이터셋·export 공통으로 메타를 고정한다. 예시 필드:

- `dataset_id`, `created_at`
- `tile_size`, `tile_overlap`, `expected_gsd_cm`, `measured_gsd_x_cm`, `measured_gsd_y_cm`, `manual_gsd_cm`, `gsd_source`, `georeferencing`
- `grid_size_meters`, `grid_size_pixels_x`, `grid_size_pixels_y`
- `mask_schema_version`, `sample_count`
- `dataset_config_snapshot_id`, `config_snapshot_path`

export 디렉터리에도 동일 스키마·`config_snapshot.yaml`을 함께 둔다.

---

## 7. 학습 export와 `tile_overlap`

타일이 겹치면 동일 지상 영역이 여러 타일에 포함될 수 있다. export·학습 파이프라인에서는 **중복 허용 / stitch 후 비중복 / 중앙 crop 등** 정책을 하나로 정하고, 본 명세 버전과 `dataset_manifest`에 기록한다 (설계서 §2.2).
