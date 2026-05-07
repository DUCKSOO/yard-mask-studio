# SAM2.1 기반 U-Net 학습용 라벨링 도구 개발 계획 (v0.3)

**문서 버전**: v0.3
**작성일**: 2026-05-07
**개발 환경**: Claude Code 기반 개발
**관련 산출물**: AX실증사업 드론 활용 AI 야드 최적운영 솔루션

**v0.3 주요 변경**: 타일 크기, 그리드 크기, overlap 등 모든 공간 파라미터를 **설정값 기반으로 동적 처리**하도록 설계 변경

---

## 1. 목적과 범위

### 1.1 목적

본 도구는 드론 정사영상에서 **U-Net 학습용 점유/비점유 세그멘테이션 라벨**을 생성하는 **내부 개발 도구**다. 최종 서비스가 아니며, 작업산출내역상 **AI-02 영역 추출 → AI-03 데이터셋 학습** 사이의 데이터 생산 단계에 해당한다.

### 1.2 1차 목표

- 정사영상을 타일로 분할 (타일 크기는 설정으로 변경 가능)
- SAM2.1 추론으로 점유 영역 mask 후보 생성
- 사람이 mask를 선택/수정/확정
- U-Net 학습용 `image + mask` 데이터셋으로 저장

### 1.3 본 계획에서 제외하는 항목

| 제외 항목 | 사유 |
|---|---|
| YOLO 다중 클래스(사람/차량/장비) 인식 | 후처리 단계에서 별도 모델로 처리 |
| 개별 블록 인스턴스 분리 | 1차는 semantic segmentation에 집중 |
| ERP/MES 연동 | 학습 데이터 생성과 무관 |
| 그리드 점유율 산출 | U-Net 결과 검증 후 후속 단계 |
| 실시간 운영 UI/대시보드 | 별도 서비스 레이어 |
| PNG 입력 지원 | 수요처 드론·정사 인도 시점이 불확실할 수 있어 1차는 GeoTIFF로만 구현하되, 동일 파이프를 유지하도록 **입력 래스터 추상화(§9.1)**로 경계를 둔다. PNG 등은 추후 동일 인터페이스로 확장 |

---

## 2. 설정 기반 설계 원칙 (핵심)

### 2.1 동적 파라미터로 처리할 항목

설정은 **변경 빈도·영향 범위·비밀 여부**에 따라 세 계층으로 분리한다. 코드에 하드코딩하지 않는다.

| 계층 | 예시 | 저장 위치 | 언제 반영? |
|---|---|---|---|
| **환경 의존 (비밀·경로)** | DB 경로, 체크포인트 절대경로, secret key | `.env` / 환경변수 | 서버 시작 시 고정 |
| **운영 고정값 (시드)** | 기본 CRS, edge_padding, split_ratio | `LABELING_CONFIG_PATH`로 지정한 YAML (`config/labeling.dev.yaml` 또는 `config/labeling.prod.yaml`) | 첫 실행 시 DB로 import; 이후 DB 우선 |
| **런타임 변경 가능** | tile_size, overlap, grid, GSD, SAM 모델, 클래스 정의 | **SQLite `active_config` 테이블** | API `POST /api/config` 호출 즉시 반영 |

서버 시작 시 DB의 활성 설정(`active_config`)을 메모리에 로드한다. DB에 행이 없으면 `LABELING_CONFIG_PATH`가 가리키는 YAML(`config/labeling.dev.yaml` 등)을 시드로 import한다. 이후 변경은 API를 통해서만 이루어지며, 변경 전 설정은 자동으로 스냅샷에 보존된다.

**설정 변경과 데이터셋 불변성 원칙**

`active_config`는 **새 데이터셋을 생성할 때 사용하는 기본 템플릿**이다. 이미 생성된 데이터셋의 타일·라벨은 생성 시점에 고정된 `dataset_config_snapshot`에 묶인다.

| 개념 | 역할 |
|---|---|
| `active_config` | 새 데이터셋 생성 시 사용할 기본 설정 (변경 가능) |
| `dataset_config_snapshot` | 특정 데이터셋에 **고정된 불변 설정** (생성 후 변경 불가) |
| 타일 / 라벨 / export | 항상 `dataset_config_snapshot_id`를 참조 |

`tile_size`·`overlap` 등을 변경하면 **기존 데이터셋에는 영향을 주지 않으며**, 새 설정을 적용하려면 반드시 **새 데이터셋 버전을 생성**해야 한다.

**런타임 변경 가능한 파라미터 목록**

| 파라미터 | 설명 | 예시 값 | 변경 빈도 |
|---|---|---|---|
| `tile_size` | 타일 한 변의 픽셀 수 | 512, 1024, 2048 | 실험에 따라 자주 |
| `tile_overlap` | 타일 간 겹침 픽셀 수 | 64, 128, 256 | 자주 |
| `grid_size_meters` | 그리드 한 변의 미터 단위 크기 | 15.0, 20.0 | 협의에 따라 |
| `expected_gsd_cm` | 기대 GSD (cm/px): GeoTIFF 실제값 검증 기준. 설정값과 실제값 차이가 `gsd_tolerance` 이상이면 경고 | 1.5, 2.0, 3.0 | 드론/고도에 따라 |
| `manual_gsd_cm` | 수동 GSD (cm/px): PNG 등 비지리참조 이미지일 때만 사용. GeoTIFF 경로에서는 무시됨 | 2.0 | PNG 사용 시만 |
| `nodata_skip_threshold` | 타일 NoData 비율 임계값 | 0.8 | 실험에 따라 |
| `sam_model_variant` | SAM 모델 종류 | "hiera_large", "hiera_base" | PC 사양에 따라 |
| `mask_classes` | 클래스 정의 | 아래 별도 정의 | 가이드라인 변경 시 |

### 2.2 설정 변경에 따른 영향 범위

| 변경 항목 | 영향 받는 단계 | 자동 재계산 가능? | 재학습 필요? |
|---|---|---|---|
| `tile_size` 변경 | 타일 생성, 학습 | 새 타일은 자동 재생성 | **예** (모델 재학습 필요) |
| `tile_overlap` 변경 | 타일 생성, stitching | 자동 재생성 | 아니오 |
| `grid_size_meters` 변경 | 후처리(점유율 계산) | 자동 재계산 | 아니오 (모델은 그리드 모름) |
| `expected_gsd_cm` 변경 | 검증 기준만 변경 | 해당 없음 | 아니오 |
| `manual_gsd_cm` 변경 (PNG만 해당) | 모든 픽셀↔미터 변환 | 자동 재계산 | 아니오 (메타정보만 갱신) |
| `mask_classes` 변경 | 라벨, 학습 | **수동 마이그레이션 필요** | **예** |

**학습용 export와 `tile_overlap`**: 표의 「재학습 필요 아니오」는 **U-Net 가중치를 다시 학습할 필요 없음**을 뜻한다. 타일이 겹치면 동일 지상 영역이 여러 타일에 포함될 수 있으므로, **export·학습 파이프라인에서는 정책을 하나로 고른다**—예: (a) 모든 타일을 그대로 두어 중복 학습 샘플을 허용하거나, (b) stitch 후 비중복 crop만 내보내거나, (c) 중앙 영역만 사용 등. 구체 규칙은 `docs/dataset_spec.md`와 `dataset_manifest`에 기록한다.

**핵심 인사이트**: 그리드 크기는 **모델이 직접 학습하는 정보가 아니다**. 모델은 픽셀 단위 점유 mask만 생성하고, 그리드 단위 점유율은 **후처리 단계에서 계산**한다. 따라서 그리드 크기 변경은 모델에 영향을 주지 않는다.

### 2.3 설정 계층 구조

**계층 1 — `.env` (환경 의존·비밀)**

```dotenv
# .env  (git에 커밋하지 않음)
DATABASE_URL=sqlite:///./data/labeling.db
SAM_CHECKPOINT_PATH=/models/sam2.1_hiera_large.pt
SECRET_KEY=...
```

**계층 2 — `config/labeling.dev.yaml` / `config/labeling.prod.yaml` (시드·초기값)**

서버 첫 실행 시 DB로 import된다. 이후에는 DB 값이 우선이며, YAML은 "초기 기본값" 역할만 한다. 사용할 파일은 `.env`의 `LABELING_CONFIG_PATH`로 지정한다.

```yaml
# config/labeling.dev.yaml  (git에 커밋)
tiling:
  tile_size: 1024
  tile_overlap: 128
  nodata_skip_threshold: 0.8
  edge_padding_strategy: "zero"  # "zero" | "reflect" | "drop"

geo:
  # GeoTIFF 경로: GeoTransform에서 measured_gsd_cm 자동 계산.
  # expected_gsd_cm은 실제값과 비교하는 검증 기준으로만 사용.
  # 차이가 gsd_tolerance 이상이면 경고 (처리는 계속).
  expected_gsd_cm: 2.0
  gsd_tolerance: 0.5
  # PNG 경로(비지리참조)에서만 사용. GeoTIFF 경로에서는 무시.
  manual_gsd_cm: null
  default_crs: "EPSG:5186"

grid:
  size_meters: 15.0
  # 그리드 기준 원점: 전체 정사영상의 연속된 격자를 유지하려면 source_image_top_left 사용.
  # tile_top_left는 타일마다 격자가 따로 시작되므로 디버그/로컬 확인 용도로만 사용.
  origin: "source_image_top_left"  # "source_image_top_left" | "geo_origin" | "tile_top_left"(디버그 전용)

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
    - id: 255
      name: "ignore"
      color: "#808080"

dataset:
  output_root: "data/exports"
  split_ratio:
    train: 0.7
    val: 0.15
    test: 0.15
  image_format: "png"
  mask_format: "png"
```

**계층 3 — SQLite `active_config` 테이블 (런타임 변경)**

API `POST /api/config`로 수정하며, 변경 전 값은 자동으로 `config_change_snapshots` 테이블에 기록된다. 서버 메모리의 현재 설정은 변경 직후 다음 요청부터 반영된다.

```sql
-- active_config: 새 데이터셋 생성 시 사용할 기본 템플릿 (항상 정확히 1행)
CREATE TABLE active_config (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    config_json TEXT    NOT NULL,   -- LabelingConfig JSON
    updated_at  TEXT    NOT NULL
);

-- active_config 변경 이력 / rollback 용도
CREATE TABLE config_change_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    config_json TEXT    NOT NULL,
    reason      TEXT,               -- "user_edit" | "rollback"
    created_at  TEXT    NOT NULL
);

-- 특정 데이터셋에 고정된 불변 설정 스냅샷
-- 타일·라벨·export는 모두 이 테이블의 id를 참조
-- tenant_id 포함: API가 tenant 단위이므로 dataset_id는 테넌트 내에서만 유일
CREATE TABLE dataset_config_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   TEXT    NOT NULL,
    dataset_id  TEXT    NOT NULL,
    config_json TEXT    NOT NULL,         -- 생성 시점 설정 전체 (이후 변경 불가)
    created_at  TEXT    NOT NULL,
    UNIQUE (tenant_id, dataset_id)
);
```

| 테이블 | 목적 |
|---|---|
| `active_config` | 새 데이터셋 생성 시 사용할 현재 기본 설정 |
| `config_change_snapshots` | 설정 변경 이력 / rollback 용 |
| `dataset_config_snapshots` | 데이터셋별 고정 설정 (생성 후 변경 불가) |

**active_config 변경 절차**:
1. `POST /api/config`로 `active_config` 갱신 → 이전 값을 `config_change_snapshots`에 보존 → 기존 데이터셋 영향 없음
2. `POST /api/tenants/{tenant_id}/datasets` 호출 시 현재 `active_config`가 새 `dataset_config_snapshot`으로 복사되어 데이터셋에 고정
3. 이후 해당 데이터셋의 타일·라벨·export는 고정된 스냅샷 기준으로만 동작

**그리드 픽셀 크기·오버레이 정렬**

- 픽셀 크기 계산: GeoTIFF는 `measured_gsd_x_cm` / `measured_gsd_y_cm`, PNG(비지리참조)는 `manual_gsd_cm` 사용.
  - `measured_gsd_x_cm`과 `measured_gsd_y_cm`의 차이가 `gsd_tolerance` 이내이면 단일값(`grid_size_pixels`)을 사용한다.
  - 차이가 크면 `grid_size_pixels_x` / `grid_size_pixels_y`로 분리하거나 경고를 발생시킨다.
- 기준 원점: 기본값 `source_image_top_left` — 전체 정사영상의 픽셀 (0, 0)을 기준으로 격자를 계산한 뒤 타일 내 좌표로 변환. 이렇게 해야 타일 경계에서 그리드가 연속된다.
- `tile_top_left`는 타일마다 (0, 0)이 기준이 되어 격자가 따로 놀 수 있으므로 **디버그 전용** 옵션으로 둔다.
- 반올림 정책(floor)이나 origin을 바꾸면 스펙 버전을 올린다.

### 2.4 데이터셋별 설정 스냅샷

각 데이터셋 export 시점의 설정값은 **불변(immutable)** 하게 함께 저장된다. 추후 설정이 바뀌어도 과거 데이터셋의 의미가 보존된다.

```
data/
  source/
    {tenant_id}/
      raw_geotiff/              # 원본 GeoTIFF

  datasets/
    {tenant_id}/
      {dataset_id}/
        images/
        masks/
        metadata/
        splits/
        config_snapshot.yaml   # 데이터셋 생성 시점의 불변 설정
        classes.json
        dataset_manifest.json

  exports/
    {tenant_id}/
      {dataset_id}/
        {export_id}/            # U-Net export 결과물
          images/
          masks/
          splits/
          classes.json
          dataset_manifest.json
          config_snapshot.yaml
```

`dataset_manifest.json`에 다음 정보가 포함된다:

```json
{
  "dataset_id": "20260507_v1",
  "created_at": "2026-05-07T10:30:00",
  "tile_size": 1024,
  "tile_overlap": 128,
  "expected_gsd_cm": 2.0,
  "measured_gsd_x_cm": 2.03,
  "measured_gsd_y_cm": 2.01,
  "manual_gsd_cm": null,
  "gsd_source": "geotiff_transform",
  "georeferencing": "full",
  "grid_size_meters": 15.0,
  "grid_size_pixels_x": 740,
  "grid_size_pixels_y": 746,
  "mask_schema_version": "1.0",
  "sample_count": 250,
  "dataset_config_snapshot_id": 1,
  "config_snapshot_path": "config_snapshot.yaml"
}
```

---

## 3. 타일 크기 운영 정책

### 3.1 도구 설계 관점

**도구는 어떤 타일 크기든 처리할 수 있도록 설계한다**. 256, 512, 1024, 2048 등 어떤 값이 들어와도 동일하게 동작한다. 로직은 다음 슈도코드 수준이다:

```python
def generate_tiles(image, tile_size, overlap):
    stride = tile_size - overlap
    for y in range(0, image.height, stride):
        for x in range(0, image.width, stride):
            tile = read_window(image, x, y, tile_size, tile_size)
            yield tile, x, y
```

**경계 타일**: 위 루프는 이미지 우하단까지 덮되, 마지막 열·행에서 `read_window` 크기가 `tile_size`보다 작을 수 있다. 이 **부분 타일**은 §9.1의 `edge_padding_strategy`로 처리한다—`zero`/`reflect`는 부족 분을 채워 `tile_size` 고정, `drop`은 해당 윈도를 버리거나 별도 정책으로 문서화한다. 구현 시 슈도코드와 동일한 stride·경계 규칙을 유지한다.

타일 크기에 따라 분기되는 로직은 없다.

### 3.2 학습 관점에서의 권장

본 프로젝트의 그리드 단위(15m 또는 20m)와 GSD를 고려한 권장 타일 크기:

| GSD | 그리드 15m | 그리드 20m | 권장 타일 크기 |
|---|---|---|---|
| 1.5 cm/px | 1000 px | 1333 px | 1024 또는 2048 |
| 2.0 cm/px | 750 px | 1000 px | 1024 |
| 3.0 cm/px | 500 px | 667 px | 512 또는 1024 |

**원칙**: 타일이 그리드 1개 이상을 담을 수 있어야 한다 (`tile_size >= grid_pixels`). 이 검증은 도구가 자동으로 수행하고, 위반 시 경고를 띄운다.

### 3.3 설정 변경 절차

타일 크기를 변경할 때:

1. `POST /api/config`로 `tile_size` 변경 → `active_config` 갱신 (기존 데이터셋 영향 없음)
2. `POST /api/tenants/{tenant_id}/datasets`로 새 데이터셋 생성 → 새 설정이 `dataset_config_snapshot`에 고정
3. `POST /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles/generate`로 타일 재생성
4. 기존 라벨 마이그레이션 여부 결정:
   - 동일 위치의 라벨이 있으면 새 타일에 자동 매핑 시도
   - 매핑 실패 시 재라벨링 큐로 이동

그리드 크기를 변경할 때:

1. `POST /api/config`로 `grid_size_meters` 변경
2. 후처리 단계에서 그리드 재계산만 수행 (라벨/모델 영향 없음)
3. 추론 결과 시각화에 새 그리드 적용

---

## 4. 라벨 클래스 정의

### 4.1 1차 클래스

| 픽셀 값 | 클래스 | 정의 |
|---:|---|---|
| 0 | `non_occupied` | **분석 대상 야드 내부**의 노출 바닥 중 적치물이 없는 영역. 통로 포함. 야드 외부·건물·도로는 포함하지 않는다. |
| 1 | `occupied` | 블록, 자재, 적치물로 인해 실제 점유된 영역 |
| 255 | `ignore` | 야드 외부, 건물, 도로, 강한 그림자, 방수포 아래, 사람/차량/장비, 작업 중 구역, 경계 애매한 영역 |

> **주의**: 야드 외부·경계 불명확 영역은 반드시 `ignore(255)`로 처리한다. `non_occupied(0)`로 라벨링하면 모델이 야드 외부를 "빈 공간"으로 학습할 수 있다.

`passage`(통로)는 별도 클래스로 두지 않으며, `non_occupied`로 라벨링한 뒤 그리드 정보와 결합하여 후처리 단계에서 구분한다.

### 4.2 클래스 확장 정책

- 클래스 추가/변경 시 `mask_schema_version`을 올린다 (예: 1.0 → 2.0)
- 기존 데이터는 마이그레이션 스크립트로 변환
- 학습 코드는 `mask_schema_version`을 확인하여 호환성 검증

---

## 5. 데이터 격리 정책

요구사항 정의서 BR-03(멀티테넌시)을 고려하여, 라벨링 단계부터 테넌트별 격리 구조를 유지한다.

```
data/datasets/
  {tenant_id}/
    {dataset_id}/
      images/
      masks/
      metadata/
      config_snapshot.yaml
```

테넌트 ID는 정사영상 메타데이터에서 자동 추출되거나, 업로드 시 명시된다. API 레벨에서 모든 요청은 `tenant_id` 검증을 거친다.

---

## 6. 데이터셋 구조

### 6.1 디렉토리 구조

```
data/datasets/
  {tenant_id}/
    {dataset_id}/
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

      config_snapshot.yaml
      classes.json
      dataset_manifest.json
```

> **`data/datasets`와 `data/exports` 관계**: `datasets`는 라벨링 작업의 원본 데이터(타일 이미지·mask·메타데이터)를 보관하며 라벨러가 직접 편집하는 대상이다. `exports`는 U-Net 학습 파이프라인에 전달할 **최종 산출물**로, `datasets`에서 split·검증·포맷 변환을 거쳐 생성된다. 두 경로 모두 `{tenant_id}/{dataset_id}` 계층으로 격리된다. 상세 규칙은 `docs/dataset_spec.md`에 명시한다.

### 6.2 mask PNG 규칙

- 원본 이미지와 동일한 크기
- 8-bit grayscale PNG
- 픽셀 값 = 클래스 ID
- 컬러 mask 저장 금지 (학습용은 반드시 class index mask)

### 6.3 타일 메타데이터 스키마

```json
{
  "tile_id": "tile_000001",
  "tenant_id": "tenant_001",
  "source_image": "yard_2026_001.tif",
  "tile_size": 1024,
  "x": 1024,
  "y": 2048,
  "overlap": 128,
  "crs": "EPSG:5186",
  "geo_transform": [126.123, 0.00002, 0, 34.567, 0, -0.00002],
  "nodata": {
    "has_nodata": false,
    "value": null,
    "source": "geotiff_metadata"
  },
  "measured_gsd_x_cm": 2.03,
  "measured_gsd_y_cm": 2.01,
  "gsd_source": "geotiff_transform",
  "expected_gsd_cm": 2.0,
  "dataset_id": "20260507_v1",
  "dataset_config_snapshot_id": 1,
  "status": "labeled",
  "mask_schema_version": "1.0",
  "created_by": "labeler_01",
  "reviewed_by": null,
  "created_at": "2026-05-07T10:30:00",
  "updated_at": "2026-05-07T10:30:00",
  "sam_model_version": "sam2.1_hiera_large",
  "sam_prompts": [
    {
      "type": "point",
      "x": 240,
      "y": 310,
      "label": "positive",
      "class": "occupied"
    }
  ]
}
```

`geo_transform`은 **GDAL GeoTransform 6원소** `[origin_x, pixel_width, row_rotation, origin_y, column_rotation, pixel_height]`와 동일 순서다. **값의 단위**는 `crs`에 따른다(EPSG:5186 등 투영 좌표계면 미터, 위경도면 도). 실제 저장 시에는 rasterio/GDAL이 반환한 값을 그대로 직렬화한다.

`measured_gsd_cm` 계산 규칙:

- **투영 좌표계(미터 단위)**: `pixel_width_m * 100 = gsd_cm`. GeoTransform의 `pixel_width`(= `abs(transform[1])`)와 `pixel_height`(= `abs(transform[5])`)를 각각 계산해 `measured_gsd_x_cm`, `measured_gsd_y_cm`으로 분리 기록한다.
- **위경도 좌표계(도 단위) 또는 GeoTransform에 rotation**(`transform[2]` 또는 `transform[4]`가 0이 아닌 경우): 단순 `pixel_width * 100`으로는 cm를 정확히 계산할 수 없다. 이 경우 **경고를 발생시키고** `gsd_source: "warning_needs_manual"`로 기록하며, 필요 시 재투영 또는 `manual_gsd_cm` 수동 입력을 요구한다.

타일 메타데이터에 `gsd_source` 필드를 추가해 GSD 계산 방식을 명시한다.

`nodata`는 임의 추정하지 않고 rasterio/GDAL 메타데이터 기준으로 기록한다—정사영상에서 픽셀값 0은 유효 데이터일 수 있으므로 `value: 0` 하드코딩을 금지한다.

### 6.4 타일 상태

| 상태 | 의미 | 다음 가능 상태 |
|---|---|---|
| unlabeled | 작업 전 | in_progress, skipped |
| in_progress | 작업 중 | labeled, skipped |
| labeled | 1차 라벨 완료 | review_needed, approved |
| review_needed | 검수 필요 | approved, rejected |
| rejected | 재작업 필요 | in_progress |
| approved | 검수 완료 | (최종) |
| skipped | 라벨링 제외 | (최종) |

---

## 7. 개발 환경 및 기술 스택

### 7.1 기술 스택

| 영역 | 기술 |
|---|---|
| 백엔드 | Python 3.11, FastAPI, SQLite (라벨 인덱스), GDAL/rasterio (GeoTIFF 처리) |
| 설정 관리 | pydantic-settings, YAML (시드), SQLite `active_config` (런타임 변경) |
| AI 추론 | PyTorch 2.x, SAM 2.1 (image predictor mode) |
| 프론트엔드 | React + TypeScript, Vite, Konva.js (캔버스) |
| 패키지 관리 | uv (Python), pnpm (Node) |
| 테스트 | pytest, vitest |

### 7.2 Claude Code 개발 가이드라인

1. **백엔드 우선 개발**: CLI에서 모든 기능을 검증한 후 프론트엔드 작업 시작
2. **Phase별 독립 세션**: 각 Phase는 별도 Claude Code 세션으로 작업하여 컨텍스트 분리
3. **테스트 코드 동반 작성**: 각 모듈은 단위 테스트와 함께 작성
4. **타입 힌트 필수**: Python pydantic, TypeScript 엄격 모드
5. **API 스키마 우선**: OpenAPI 스펙을 먼저 작성한 후 구현
6. **설정값 하드코딩 금지**: 모든 공간 파라미터는 config 객체에서 주입

---

## 8. 모듈 구성

```
yard-mask-studio/
│
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py           # 설정 로더: 시작 시 DB → YAML 시드 순으로 로드, app.state에 주입
│   │   │   ├── config_schema.py    # LabelingConfig pydantic 스키마 (계층별 분리)
│   │   │   ├── config_store.py     # active_config CRUD + 스냅샷 저장/롤백
│   │   │   ├── db.py               # 1차 SQLite; 저장소 추상화 시 교체 용이 (§17)
│   │   │   └── tenant.py           # 테넌트 격리 로직
│   │   ├── tiling/
│   │   │   ├── raster_source.py    # 입력 래스터 추상화 (1차: GeoTIFF, 추후 PNG·world file 등)
│   │   │   ├── tile_generator.py   # RasterSource → 타일 (tile_size 주입)
│   │   │   ├── tile_index.py       # 타일 인덱스 관리
│   │   │   └── coordinate_utils.py # 픽셀↔미터 변환 (GSD 주입)
│   │   ├── grid/
│   │   │   ├── grid_calculator.py  # 그리드 크기 계산 (grid_size_meters 주입)
│   │   │   └── grid_overlay.py     # 추후 추론 결과에 그리드 매핑
│   │   ├── sam/
│   │   │   ├── sam_predictor.py    # SAM 추론 (SegmentationBackend 프로토콜 → §17)
│   │   │   └── prompt_handler.py   # prompt 변환/검증
│   │   ├── annotation/
│   │   │   ├── mask_service.py     # mask 저장·편집
│   │   │   ├── review_queue.py     # 검수 큐 관리
│   │   │   └── migration.py        # 스키마 변경 시 라벨 마이그레이션
│   │   ├── dataset/
│   │   │   ├── dataset_exporter.py # U-Net 학습용 export (포맷 플러그인 확장 → §17)
│   │   │   ├── split_generator.py  # train/val/test 분할
│   │   │   ├── validator.py        # 데이터셋 무결성 검증
│   │   │   └── config_snapshot.py  # export 시 설정 스냅샷 저장
│   │   └── api/
│   │       ├── routes.py
│   │       └── schemas.py          # pydantic 요청/응답 스키마
│   ├── tests/
│   └── scripts/
│       └── cli.py                  # CLI 검증 도구
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── TileViewer.tsx      # 타일 zoom/pan (Konva)
│   │   │   ├── MaskCanvas.tsx      # mask 편집 캔버스
│   │   │   ├── ClassPanel.tsx      # occupied/ignore 토글
│   │   │   ├── ToolBar.tsx
│   │   │   ├── TileNavigator.tsx   # 타일 목록·상태 필터
│   │   │   ├── ReviewPanel.tsx     # 검수 승인/거부
│   │   │   └── GridOverlay.tsx     # 그리드 시각화 (설정 기반)
│   │   ├── api/
│   │   │   └── client.ts           # axios + zod API 클라이언트
│   │   └── stores/
│   │       ├── annotationStore.ts  # mask 상태 + undo/redo 히스토리
│   │       └── configStore.ts      # 서버 설정 동기화
│   ├── package.json
│   └── vite.config.ts
│
├── config/
│   ├── labeling.dev.yaml           # 개발 환경 시드 (git 커밋)
│   └── labeling.prod.yaml          # 운영 환경 시드 (git 커밋)
│
├── data/                           # .gitignore 제외
│   ├── source/
│   │   └── {tenant_id}/
│   │       └── raw_geotiff/        # 원본 GeoTIFF
│   ├── datasets/
│   │   └── {tenant_id}/
│   │       └── {dataset_id}/       # 타일·mask·메타데이터·config_snapshot
│   └── exports/
│       └── {tenant_id}/
│           └── {dataset_id}/
│               └── {export_id}/    # U-Net export 결과물
│
├── models/                         # .gitignore 제외 (SAM 체크포인트)
│
├── docs/
│   ├── labeling_guide.md           # 라벨링 기준표 (시각 예시 포함)
│   ├── api_spec.yaml               # OpenAPI 3.0 스펙
│   ├── dataset_spec.md             # 데이터셋 구조 명세
│   └── config_guide.md             # 설정 변경 가이드
│
├── .env.example
├── .gitignore
├── pyproject.toml                  # uv 기반 Python 의존성
├── labeling-tool-plan-v3.md
└── README.md
```

### 8.1 핵심 설정 객체 예시

```python
# backend/app/core/config_schema.py
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class TilingConfig(BaseModel):
    tile_size: int = Field(default=1024, ge=128, le=4096)
    tile_overlap: int = Field(default=128, ge=0)
    nodata_skip_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    edge_padding_strategy: str = Field(default="zero")

    @model_validator(mode="after")
    def check_overlap(self) -> "TilingConfig":
        if self.tile_overlap >= self.tile_size:
            raise ValueError("overlap must be smaller than tile_size")
        return self

class GridConfig(BaseModel):
    size_meters: float = Field(default=15.0, gt=0)
    # tile_top_left는 타일마다 격자가 따로 시작되므로 디버그 전용
    origin: Literal[
        "source_image_top_left",  # 기본값: 전체 정사영상 기준 연속 격자
        "geo_origin",             # 지리 원점(CRS 기준) 사용 시
        "tile_top_left",          # 디버그 전용
    ] = "source_image_top_left"

    def to_pixels(self, gsd_x_cm: float, gsd_y_cm: float) -> tuple[int, int]:
        """x/y 그리드 픽셀 크기 반환. floor 사용; 정책 변경 시 스펙 버전을 올릴 것."""
        return (
            int(self.size_meters * 100 / gsd_x_cm),
            int(self.size_meters * 100 / gsd_y_cm),
        )

class GeoConfig(BaseModel):
    # GeoTIFF: measured_gsd_cm은 런타임에 GeoTransform에서 계산.
    # expected_gsd_cm은 실제값 검증 기준으로만 사용.
    expected_gsd_cm: float = Field(default=2.0, gt=0)
    gsd_tolerance: float = Field(default=0.5, ge=0)
    # PNG 등 비지리참조 입력일 때만 사용. GeoTIFF 경로에서는 무시.
    manual_gsd_cm: float | None = Field(default=None, gt=0)
    default_crs: str = "EPSG:5186"

class LabelingConfig(BaseModel):
    tiling: TilingConfig
    grid: GridConfig
    geo: GeoConfig
    # ... 기타 섹션 (sam, classes, dataset)
```

```python
# backend/app/core/config.py
from pathlib import Path
import yaml
from app.core.config_schema import LabelingConfig
from app.core.config_store import load_active_config, seed_from_yaml

import os

# 환경변수로 dev/prod 시드 파일 경로를 선택 (.env에서 지정)
YAML_SEED = Path(os.getenv("LABELING_CONFIG_PATH", "config/labeling.dev.yaml"))

def get_startup_config() -> LabelingConfig:
    """서버 시작 시 한 번 호출. DB → YAML 시드 순으로 로드."""
    config = load_active_config()
    if config is None:
        config = seed_from_yaml(YAML_SEED)  # 첫 실행: YAML을 DB에 저장
    return config
```

```python
# backend/app/core/config_store.py
import json
from datetime import datetime, UTC
from app.core.db import get_db
from app.core.config_schema import LabelingConfig

def load_active_config() -> LabelingConfig | None:
    row = get_db().execute("SELECT config_json FROM active_config WHERE id=1").fetchone()
    return LabelingConfig.model_validate_json(row["config_json"]) if row else None

def save_active_config(new: LabelingConfig, reason: str = "user_edit") -> None:
    db = get_db()
    old = load_active_config()
    if old:  # 이전 값을 변경 이력으로 보존
        db.execute(
            "INSERT INTO config_change_snapshots (config_json, reason, created_at) VALUES (?,?,?)",
            (old.model_dump_json(), reason, datetime.now(UTC).isoformat()),
        )
    db.execute(
        "INSERT OR REPLACE INTO active_config (id, config_json, updated_at) VALUES (1,?,?)",
        (new.model_dump_json(), datetime.now(UTC).isoformat()),
    )
    db.commit()
```

### 8.2 의존성 주입 예시

```python
# backend/app/tiling/tile_generator.py
class TileGenerator:
    def __init__(self, config: TilingConfig):
        self.tile_size = config.tile_size
        self.overlap = config.tile_overlap
        self.skip_threshold = config.nodata_skip_threshold

    def generate(self, image_path: str) -> Iterator[Tile]:
        # tile_size, overlap에 따라 동작
        # 어떤 값이든 동일 로직
        ...
```

---

## 9. 핵심 기능 정의

### 9.1 타일 생성

**입력(1차)**: GeoTIFF 정사영상 + TilingConfig  
**출력**: 타일 이미지 + 메타데이터 JSON

**입력 경계(확장 대비)**: 읽기 전용 **입력 래스터 추상화**(`RasterSource` 등) 뒤에 GeoTIFF 구현(`rasterio`)을 둔다. 타일 생성·SAM·저장 로직은 **픽셀 배열 + (있으면) CRS·affine·nodata**만 소비한다. **PNG 등 비지리참조 포맷은 1차 범위에서 제외**하되, 추후 동일 인터페이스의 구현체로 추가한다.

**입력 유형별 GSD 처리**

| 입력 유형 | 사용 GSD | 비고 |
|---|---|---|
| GeoTIFF (투영 좌표계) | `measured_gsd_x_cm`, `measured_gsd_y_cm` (GeoTransform 계산) | `expected_gsd_cm`은 검증 기준으로만 사용 |
| PNG + world file | world file 또는 sidecar metadata | 추후 구현 시 지정 |
| PNG 등 비지리참조 | `manual_gsd_cm` (필수 입력) | 미입력 시 오류 |

manifest에 지리참조 수준(`georeferencing: "full"` / `"gsd_only"` / `"none"`)을 기록한다. `expected_gsd_cm`은 실제 픽셀↔미터 변환에 사용하지 않는다.

**처리 규칙**:
- 원본 해상도 유지 (다운샘플링 금지)
- GeoTIFF 경로에서는 rasterio의 windowed read 사용 (메모리 절약)
- 좌표계(CRS), GeoTransform 보존 (GeoTIFF 입력 시)
- 가장자리 부족 영역은 설정의 `edge_padding_strategy`에 따라 처리
- NoData 영역 비율이 `nodata_skip_threshold` 이상인 타일은 자동 skip

### 9.2 SAM 추론

**입력 prompt**:

| 타입 | 설명 |
|---|---|
| positive point | 점유 영역 내부 클릭 |
| negative point | 제외 영역 클릭 |
| box | 블록/자재 영역 박스 |
| point + box 조합 | 정밀 추출 |

**출력**:
- mask 후보 최대 N개 (`sam.max_candidates` 설정)
- bbox, area, score 포함
- RLE 인코딩으로 전송 (페이로드 절감)

**API 스펙 메모**: OpenAPI(`docs/api_spec.yaml`)에 응답 필드로 RLE(또는 COCO-style polygon/`counts`)와 타일 크기를 명시하고, 프론트는 디코딩 후 캔버스 마스크로 그린다. 대안으로 **작은 타일 mask는 zlib PNG(base64)** 등으로 줄 수 있으나, 기본은 RLE로 통일해 페이로드·호환성을 맞춘다.

### 9.3 라벨 편집

**저장 원칙**: 저장 시점에는 항상 **최종 class index mask**를 저장한다. SAM mask 후보는 일시적 결과이며, `mask_id`만으로는 최종 라벨을 복원할 수 없다. 저장 직전에 편집된 모든 layer를 합성하여 단일 class index mask PNG로 확정한다.

**v0.1 필수**:
- mask 선택·삭제(SAM 후보 중 선택·제외 등), 저장된 mask 로드
- class 지정 (occupied / ignore)
- save: 최종 합성된 class index mask RLE를 API에 전송, 서버에서 PNG로 저장
- load: 저장된 class index mask PNG를 로드해 캔버스에 표시
- undo / redo (최근 20단계; mask 상태 스냅샷 기반)

**v0.2 추가**(매트릭스 §12와 동일):
- mask 병합·삭제(편집 도구)
- brush add / erase (반경 조정 가능)
- mask 외곽선 수동 보정

brush·병합 등 v0.2 편집도 Phase 2에서 구축한 **동일 undo/redo 스택**으로 처리한다.

**v0.3 후순위**:
- polygon edit
- multi-user lock
- U-Net pre-label 불러오기

### 9.4 그리드 오버레이 (시각화 전용)

라벨링 작업 자체에는 그리드가 영향을 주지 않지만, **시각 참고용**으로 그리드를 표시할 수 있다.

- `grid.size_meters`와 타일 메타데이터의 GSD(GeoTIFF: `measured_gsd_x_cm` / `measured_gsd_y_cm`, 비지리참조: `manual_gsd_cm`)로부터 픽셀 단위 그리드 크기 계산 (§2.3 원점·내림 정책과 일치)
- 캔버스에 반투명 그리드 라인 오버레이
- 그리드 표시 on/off 토글
- 그리드 크기 변경 시 즉시 시각 반영 (재라벨링 불필요)

### 9.5 검수 워크플로

- 라벨러는 `labeled` 상태로 저장
- 검수자는 `review_needed` 큐에서 작업 가져오기
- 승인 → `approved`, 거부 → `rejected` + 코멘트
- 거부된 작업은 원 라벨러에게 재할당

---

## 10. API 설계

### 10.1 설정 관련

```
GET    /api/config                      # 현재 활성 설정 조회 (DB에서 읽음)
POST   /api/config                      # 설정 변경 (영향도 검증 → config_change_snapshots 저장 → DB 갱신 → 메모리 반영)
POST   /api/config/validate             # 변경 전 영향도 분석만 수행 (저장 없음)
POST   /api/config/rollback/{snapshot_id}  # config_change_snapshots에서 특정 버전으로 되돌리기
GET    /api/config/snapshots            # config_change_snapshots 목록 (변경 이력)
GET    /api/config/snapshots/{id}       # 특정 변경 이력 조회
```

`POST /api/config` 처리 순서:
1. 요청 body를 `LabelingConfig`로 검증 (pydantic)
2. 현재 설정과 비교해 영향도 계산 (`tile_size` 변경이면 재생성 경고 등)
3. 현재 설정을 `config_change_snapshots`에 저장 (`reason: "user_edit"`)
4. `active_config` 갱신
5. `app.state.config` 갱신 → 다음 요청부터 즉시 반영

`mask_classes` 변경(schema_version 증가)은 추가로 마이그레이션 잠금·컨펌 단계가 필요하다.

### 10.2 데이터셋 관련 (신규)

데이터셋 생성 시 현재 `active_config`가 `dataset_config_snapshots`에 고정된다. 이후 타일·라벨·export는 모두 해당 스냅샷을 참조한다.

```
POST   /api/tenants/{tenant_id}/datasets                              # 데이터셋 생성 (active_config → snapshot 복사)
GET    /api/tenants/{tenant_id}/datasets                              # 데이터셋 목록
GET    /api/tenants/{tenant_id}/datasets/{dataset_id}                 # 데이터셋 상세
GET    /api/tenants/{tenant_id}/datasets/{dataset_id}/config          # 해당 데이터셋의 고정 설정 조회
POST   /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles/generate  # 타일 생성
POST   /api/tenants/{tenant_id}/datasets/{dataset_id}/export/unet     # U-Net export
```

### 10.3 타일 관련

타일은 반드시 `dataset_id` 컨텍스트 하에 조회한다. 동일한 원본 이미지에서 설정이 다른 여러 데이터셋을 만들 수 있으므로 `tile_id`는 데이터셋 내에서만 유일하다.

```
GET    /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles?status=unlabeled&limit=20
GET    /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/image
GET    /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/metadata
PATCH  /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/status
```

### 10.4 SAM 추론

`tile_id`는 데이터셋 내에서만 유일하므로, SAM 추론도 반드시 `tenant_id` / `dataset_id` 컨텍스트를 포함한다.

```
POST   /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/sam/predict
```

요청:
```json
{
  "prompts": [
    { "type": "point", "x": 240, "y": 310, "label": "positive" },
    { "type": "box", "x1": 100, "y1": 100, "x2": 400, "y2": 350 }
  ],
  "multimask_output": true
}
```

### 10.5 라벨 저장

```
POST   /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/annotation
GET    /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/annotation
DELETE /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/annotation
```

저장 요청 본문 — **최종 class index mask를 직접 저장** (MVP):

```json
{
  "status": "labeled",
  "mask_encoding": "rle",
  "class_mask": {
    "height": 1024,
    "width": 1024,
    "counts": "<COCO-style RLE counts>"
  }
}
```

> SAM mask 후보 ID(`mask_id`)만 저장하면 추후 후보가 사라진 뒤 라벨을 복원할 수 없다. 프론트에서 편집을 완료한 뒤 최종 합성 mask를 RLE로 직렬화해 전송한다. 서버는 이를 받아 PNG(`masks/tile_000001.png`)로 저장한다.

### 10.6 검수

```
GET    /api/tenants/{tenant_id}/review/queue
POST   /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/review/approve
POST   /api/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/review/reject
```

### 10.7 Export

Export는 §10.2의 데이터셋 API로 통합 (`POST /api/tenants/{tenant_id}/datasets/{dataset_id}/export/unet`).

```
GET    /api/tenants/{tenant_id}/exports/{export_id}/status
GET    /api/tenants/{tenant_id}/exports/{export_id}/download
```

Export 시 해당 데이터셋의 `dataset_config_snapshot`이 함께 저장된다.

---

## 11. 개발 로드맵

### Phase 0. 기준 정립 (1주)

| 순서 | 작업 | 산출물 |
|---:|---|---|
| 1 | 라벨링 기준표 작성 | `docs/labeling_guide.md` (시각 예시 20장 이상) |
| 2 | 설정 스키마 정의 | `config_schema.py` + `docs/config_guide.md` |
| 3 | dataset 스키마 확정 | `docs/dataset_spec.md` |
| 4 | OpenAPI 스펙 초안 | `docs/api_spec.yaml` |
| 5 | 라벨링 PC 사양 결정 | 테스트 PC 1대 셋업 |

**완료 기준**: 다른 사람이 가이드만 보고도 일관된 라벨을 만들 수 있어야 함

### Phase 1. 백엔드 핵심 (2주)

| 순서 | 작업 | 산출물 |
|---:|---|---|
| 1 | 설정 계층 구현 | core/config.py (시작 시 DB→YAML 로드), config_schema.py, config_store.py (active_config CRUD·스냅샷) |
| 2 | 입력 래스터 추상화 + rasterio GeoTIFF 구현 | raster_source.py, tile_generator.py (config 주입형) |
| 3 | 타일 생성 + 메타데이터 저장 | CLI 동작 확인 (다양한 tile_size로) |
| 4 | 좌표 변환 유틸 | coordinate_utils.py |
| 5 | 그리드 계산 | grid_calculator.py |
| 6 | SQLite 타일 인덱스 | tile_index.py + 테스트 |
| 7 | SAM 2.1 추론 모듈 | sam_predictor.py + GPU 동작 확인 |
| 8 | mask 저장/로드 | mask_service.py |
| 9 | FastAPI 라우트 연결 | 모든 API 엔드포인트 |
| 10 | CLI 라벨링 도구 | scripts/cli.py |

**완료 기준**:
- CLI만으로 타일 1장에 SAM 추론 → class index mask PNG 저장 가능
- `tile_size=512`와 `tile_size=1024`로 각각 동일 입력에 대해 정상 동작
- `grid_calculator` 단위 테스트: `grid_size_meters`가 15·20 등으로 바뀔 때 **픽셀 크기·미터 환산 결과가 기대값과 일치**(실제 야드 점유율 배치 파이프라인 연동은 본 Phase 범위 밖)

### Phase 2. 프론트엔드 v0.1 (2주)

| 순서 | 작업 | 산출물 |
|---:|---|---|
| 1 | 프로젝트 셋업 (Vite + React + TS) | 빈 프로젝트 |
| 2 | 설정 동기화 store | configStore.ts |
| 3 | TileViewer (zoom/pan) | Konva 기반 |
| 4 | API 클라이언트 | axios + zod |
| 5 | SAM prompt 입력 | point/box |
| 6 | mask overlay 표시 | 반투명 컬러 |
| 7 | 그리드 오버레이 | GridOverlay.tsx (설정 기반) |
| 8 | ClassPanel | occupied/ignore 토글 |
| 9 | save 버튼 | 백엔드 연결 |
| 10 | undo/redo | 최근 20단계 히스토리 스택 (`annotationStore`) |

**완료 기준**: GUI로 타일 1장 라벨링 → 저장 → 재로드 가능, 그리드 크기 변경 시 즉시 시각 반영, **undo/redo 20단계 동작**

### Phase 3. 라벨링 워크플로 v0.2 (2주)

| 순서 | 작업 | 산출물 |
|---:|---|---|
| 1 | 타일 목록 + 상태 필터 | TileNavigator |
| 2 | 작업 진행률 표시 | 통계 위젯 |
| 3 | brush add/erase | MaskCanvas 확장 |
| 4 | mask 병합/삭제 | 편집 도구 |
| 5 | 키보드 단축키 | 생산성 향상 (undo/redo 포함, Phase 2에서 기본 단축키 확장) |
| 6 | 검수 큐 + 승인/거부 | review_queue.py + UI |

**완료 기준**: 1명의 작업자가 100장 이상을 끊김 없이 연속 라벨링 가능

### Phase 4. Export 및 학습 연동 (1주)

| 순서 | 작업 | 산출물 |
|---:|---|---|
| 1 | dataset_exporter.py | class index mask PNG export |
| 2 | 설정 스냅샷 저장 | config_snapshot.py |
| 3 | image/mask 무결성 검증 | validator.py |
| 4 | train/val/test split | split_generator.py |
| 5 | dataset_manifest.json 생성 | 메타 정보 통합 |
| 6 | U-Net dataloader smoke test | 별도 학습 스크립트 |

**완료 기준**: export된 데이터셋으로 U-Net dataloader가 에러 없이 동작, 설정 스냅샷이 함께 저장됨

### Phase 5. 검증 및 1차 학습 (2주)

| 순서 | 작업 | 산출물 |
|---:|---|---|
| 1 | 샘플 20장 라벨링 | 테스트 라벨 |
| 2 | 라벨링 가이드 보완 | v1.1 가이드 |
| 3 | 100~300장 본 라벨링 | 1차 학습 데이터 |
| 4 | U-Net baseline 학습 | IoU, F1 측정 |
| 5 | 결과 시각 검수 | 문제 케이스 정리 |
| 6 | 다양한 tile_size 비교 실험 | 최적 tile_size 결정 |
| 7 | 가이드 / 도구 개선 | v1.2 |

**완료 기준**:
- U-Net 학습 파이프라인이 에러 없이 동작
- validation IoU / F1 산출 가능
- 예측 mask를 시각적으로 검수 가능
- 성능 저하 케이스를 유형별로 분류 가능

**1차 목표 성능 지표** (완료 기준이 아님): IoU 0.6 — 데이터 품질·다양성·class imbalance에 따라 초기 결과가 낮을 수 있으며, 이는 도구 개발 실패가 아니라 라벨 개선의 입력으로 처리한다.

---

## 12. 버전별 기능 매트릭스

| 기능 | v0.1 | v0.2 | v0.3 |
|---|---:|---:|---:|
| 설정 기반 타일링 (모든 크기 지원) | O | O | O |
| 설정 기반 그리드 계산 | O | O | O |
| SAM point prompt | O | O | O |
| SAM box prompt | O | O | O |
| mask 선택/저장 | O | O | O |
| occupied/ignore 지정 | O | O | O |
| 그리드 오버레이 시각화 | O | O | O |
| 타일 목록/상태 관리 | - | O | O |
| brush 편집 | - | O | O |
| mask 병합/삭제 | - | O | O |
| undo/redo (최근 20단계) | O | O | O |
| 검수 큐 | - | O | O |
| dataset export + 설정 스냅샷 | 수동 | O | O |
| 설정 변경 영향도 분석 | - | O | O |
| U-Net pre-label | - | - | O |
| polygon 정밀 편집 | - | - | O |
| 멀티 유저 lock | - | - | O |

---

## 13. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| SAM이 야드 블록을 잘 못 잡음 | 높음 | point + box 병행, prompt 가이드 작성 |
| 그림자/방수포 오탐 | 높음 | ignore 클래스 적극 활용, 가이드에 명시 |
| 타일 경계에서 블록 잘림 | 중간 | overlap 설정 조정 (실험으로 결정) |
| 라벨러 간 기준 차이 | 매우 높음 | Phase 0 가이드 + 시각 예시 + 검수 큐 |
| GeoTIFF 좌표계 불일치 | 중간 | 메타데이터 검증 단계 추가, 기대 GSD 검증 |
| 수요처 드론·정사영상 인도 지연 | 중간 | 입력 래스터 추상화로 PNG 등 확장 여지 유지, 내부 검증은 소형 합성 GeoTIFF로 수행 |
| SAM 추론 속도 느림 | 중간 | embedding 캐싱, image_predictor 사전 로딩 |
| GPU VRAM 부족 | 중간 | SAM Base 모델로 폴백 (설정으로 변경) |
| 정사영상이 너무 큼 | 높음 | 전체 메모리 로딩 금지, windowed read 강제 |
| U-Net 성능이 낮음 | 중간 | tile_size 변경 실험, encoder 변경 |
| 라벨 데이터 멀티테넌트 누출 | 높음 | 디렉토리 분리, API 레벨 tenant_id 검증 |
| 그리드 크기 변경 빈번 | 낮음 | 후처리 단계에서 동적 계산, 라벨 영향 없음 |
| 타일 크기 변경 시 라벨 손실 | 중간 | 데이터셋 버전 관리, 가능한 경우 자동 매핑 |
| 설정 스키마 변경 | 중간 | mask_schema_version 관리, 마이그레이션 스크립트 |

---

## 14. 완료 기준

### v0.1 완료 기준 (MVP)

- [ ] 라벨링 가이드 문서 v1.0 작성 완료
- [ ] GeoTIFF에서 설정값에 따른 타일 생성 가능 (512·1024 생성 + SAM 추론 검증, 2048은 타일 생성만 검증)
- [ ] CLI로 SAM mask 생성 → class index mask PNG 저장 동작
- [ ] GUI에서 타일 1장 라벨링 → 저장 → 재로드 가능
- [ ] undo/redo 최근 20단계 동작 (mask 편집 단계 롤백)
- [ ] 그리드 크기 변경 시 GUI 오버레이 즉시 반영
- [ ] image/mask 파일명 1:1 매칭
- [ ] 메타데이터 JSON에 `dataset_id`, `dataset_config_snapshot_id`, `measured_gsd_x_cm`, `gsd_source` 포함
- [ ] `GET /api/config`, `POST /api/config` 동작 확인 (변경 → 메모리 즉시 반영 → 스냅샷 저장)
- [ ] export 후 U-Net dataloader smoke test 통과 (라벨링 도구의 목적이 학습 데이터 생성이므로 MVP에 포함)

### v0.2 완료 기준

- [ ] 100장 이상 연속 라벨링 안정 동작
- [ ] mask 편집(brush, 병합, 삭제) 정상 동작
- [ ] 작업 상태 추적 (unlabeled → approved 흐름)
- [ ] 검수 큐 동작
- [ ] export API (`POST .../export/unet`) → 정식 dataset 구조로 저장 + U-Net dataloader 재검증 (100장 이상 기준)
- [ ] 설정 변경 시 영향도 분석 API 동작

### v0.3 완료 기준

- [ ] 100~300장으로 U-Net 1차 학습 가능
- [ ] U-Net validation IoU / F1 정상 산출
- [ ] 예측 mask 시각 검수 및 문제 케이스 유형 분류
- [ ] 라벨링 기준 문제점 정리 완료
- [ ] 다양한 tile_size 실험 결과로 최적값 결정
- [ ] 다음 단계(다중 클래스, 인스턴스) 요구사항 도출

> 1차 목표 성능 지표: IoU ≥ 0.6. 초기 데이터에서 미달 시 도구 개선이 아닌 라벨 품질·데이터 다양성 개선 이슈로 처리.

---

## 15. Claude Code 작업 우선순위

### 즉시 시작 (Phase 0)

```
1. config/labeling.dev.yaml (기본 설정 템플릿)
2. backend/app/core/config_schema.py (pydantic 스키마)
3. docs/config_guide.md (설정 변경 가이드)
4. docs/labeling_guide.md (시각 예시는 정사영상 확보 후)
5. docs/dataset_spec.md
6. docs/api_spec.yaml (OpenAPI 3.0)
```

### Phase 1 핵심 파일

```
1. backend/app/core/config.py
2. backend/app/core/config_schema.py
3. backend/app/core/config_store.py
4. backend/app/tiling/raster_source.py
5. backend/app/tiling/tile_generator.py
6. backend/app/tiling/coordinate_utils.py
7. backend/app/tiling/tile_index.py
8. backend/app/grid/grid_calculator.py
9. backend/app/sam/sam_predictor.py
10. backend/app/annotation/mask_service.py
11. backend/app/api/routes.py
12. backend/app/api/schemas.py
13. backend/scripts/cli.py
14. backend/tests/test_config_store.py (active_config 저장·로드·롤백·시드 import)
15. backend/tests/test_tile_generator.py (다양한 tile_size 테스트)
16. backend/tests/test_grid_calculator.py (다양한 grid_size 테스트)
17. backend/tests/test_sam_predictor.py
```

### Phase 2 핵심 파일

```
1. frontend/src/stores/configStore.ts
2. frontend/src/components/TileViewer.tsx
3. frontend/src/components/MaskCanvas.tsx
4. frontend/src/components/GridOverlay.tsx
5. frontend/src/components/ClassPanel.tsx
6. frontend/src/api/client.ts
7. frontend/src/stores/annotationStore.ts (mask 상태 및 undo/redo 히스토리)
```

---

## 16. 최종 개발 방향

본 도구는 복잡한 annotation 플랫폼이 아니라 다음 한 문장의 기능에 집중한다.

> **정사영상 타일을 열고, SAM 2.1로 점유 mask 후보를 만들고, 사람이 확정한 뒤, U-Net 학습용 class index mask로 저장하는 도구**

핵심 설계 원칙:

1. **모든 공간 파라미터(타일 크기, 그리드 크기, overlap, GSD)는 설정값**으로 처리한다
2. 코드는 어떤 설정값이 와도 동일하게 동작한다
3. 데이터셋은 **설정 스냅샷과 함께 저장**되어 추후 재현 가능하다
4. 그리드 크기는 **후처리 단계의 파라미터**일 뿐 모델에 영향을 주지 않는다
5. 타일 크기 변경은 모델 재학습을 요구하므로 **데이터셋 버전을 분리**한다
6. 향후 확장 가능한 교체 지점(입력 래스터·추론·Export·저장소 등)은 **§17**에 두고, 당장 구현하지 않아도 인터페이스·메타 키 이름은 통일한다

개발 순서:

1. **Phase 0**: 라벨링 기준 + 설정 스키마 + API 스펙 확정
2. **Phase 1**: 백엔드 + CLI로 모든 핵심 기능 검증 (다양한 설정값으로)
3. **Phase 2**: 최소 GUI (v0.1)
4. **Phase 3**: 라벨링 워크플로 (v0.2) + 검수
5. **Phase 4**: Export + U-Net 연동
6. **Phase 5**: 소량 라벨링 → 1차 학습 → 가이드 보완 반복

**개발 일정 — MVP와 Full 분리**

| 구분 | 범위 | 예상 기간 |
|---|---|---|
| **MVP** | Phase 0~2 + Phase 4 일부 | **4~5주** |
| **Full v0.3** | Phase 0~5 전체 | **10주** |

**MVP 범위** (Phase 0: 1주 + Phase 1: 2주 + 최소 GUI: 1~2주):
- GeoTIFF 타일링 + SAM2.1 point/box 추론
- 최소 GUI (타일 뷰어 + mask 선택 + class 지정 + save/load + undo/redo)
- 최종 class index mask 저장
- U-Net dataloader smoke test (**MVP 완료 기준에 포함**—라벨링 도구의 목적이 학습 데이터 생성이므로, dataloader까지 붙여봐야 출력 형식이 확정됨)

이 범위가 동작하면 실제 라벨링 작업을 시작할 수 있다. 이후 검수 큐·brush 편집·설정 영향도 분석·U-Net 학습 연동은 Full v0.3 단계에서 추가한다.

**1차 마일스톤**: Phase 1 완료 시점에 백엔드 + CLI만으로 다양한 설정값에 대해 U-Net 학습용 데이터 생성 가능 → 이후 GUI는 생산성 향상 도구로 추가

---

## 17. 확장 포인트 (여지)

1차 범위에 넣지 않더라도, 아래에서 **인터페이스·메타데이터·설정 키**만 미리 정해 두면 이후 확장 시 리팩터 비용이 줄어든다. 구현은 최소로 두고 **교체 가능한 경계**만 유지한다.

| 영역 | 나중에 생길 수 있는 요구 | 남겨둘 것 (설계 여지) |
|---|---|---|
| **입력 래스터** | COG·원격 URL·큰 정사 스트리밍 | `RasterSource`: 로컬 파일 외 **URI·range read** 구현체 슬롯. 타일 메타에 **dtype·밴드 수·활성 밴드** 필드 예약 |
| **비지리 PNG 등** | 이미 §9.1 | manifest **`georeferencing`**: `full` / `gsd_only` / `none`. sidecar **world file(`.pgw`)** 옵션은 PNG 구현체에서 선택 |
| **추론 백엔드** | SAM 외 모델·버전 업 | `sam_predictor`를 **`SegmentationBackend` 프로토콜**(예: `predict(tile, prompts) → masks`)으로 감싸고, 구현체 교체만 허용 |
| **장시간 작업** | 대량 타일·재생성 | SAM/타일 재생성은 동기만이 아니라 **`job_id` + 상태 폴링** 패턴을 OpenAPI에 자리만 확보 가능 |
| **Export 포맷** | COCO·GeoJSON·TFRecord 등 | `dataset_exporter`: **PNG 단일 구현 + 포맷별 writer 등록** 구조. `dataset_manifest`에 **`export_format`**, **`overlap_policy`**(중복 허용·crop 등) 필드 예약 |
| **저장소** | S3·MinIO·NAS | 타일·원본 인덱스에 **`source_uri`** (`file://`, 향후 `s3://`). 로컬 경로 하드코딩 금지 |
| **설정·테넌트** | 테넌트별 다른 타일링 | 현재 `active_config` 단일 행 가정 → 확장 시 **`tenant_id`별 행** 또는 JSON 내부 분리; API는 동일 스키마 유지 |
| **DB 엔진** | 동시 접속·운영 DB | `db.py`를 **연결 팩토리**로 두고 1차는 SQLite만 |
| **협업·락** | 멀티 유저(v0.3 후순위) | 타일 메타에 **`lock_version` 또는 `etag`**, 선택 필드 `locked_by` 예약 |
| **보안** | 외부 노출·역할 | 경로 `tenant_id`만으로는 부족할 수 있음 → **인증·API 키**는 별도 레이어로 추가 가능함을 전제 |
| **후처리 경계** | YOLO·점유율 그리드·ERP | §1.3 제외 항목 유지. 본 도구 출력은 **픽셀 mask + 스냅샷**까지; 이후 파이프는 **별도 서비스**로 연결 |

**원칙**: 불확실한 기능은 구현하지 않되, **교체 지점 이름**(프로토콜·키 이름·manifest 필드)만 계획서와 OpenAPI에 맞춰 둔다.
