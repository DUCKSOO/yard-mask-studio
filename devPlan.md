---
name: 개발 순서 계획
overview: labeling-tool-plan-v3.md 기반으로, 현재 빈 레포에서 MVP(Phase 0~2 + Export smoke test)까지의 개발 순서를 단계별로 정의한다. 각 단계는 다음 단계의 전제 조건이 된다.
todos:
  - id: step0-env
    content: "Step 0: pyproject.toml, frontend/package.json, 디렉토리 골격, .env 구성"
    status: pending
  - id: step1-spec
    content: "Step 1: config/labeling.dev.yaml, config_schema.py, dataset_spec.md, api_spec.yaml, labeling_guide.md"
    status: pending
  - id: step2-backend
    content: "Step 2: 백엔드 핵심 모듈 구현 (설정계층 → 타일링 → 그리드 → SAM → Annotation → API + 테스트)"
    status: pending
  - id: step3-cli
    content: "Step 3: CLI 엔드-투-엔드 검증 (GeoTIFF → 타일 → SAM → mask PNG)"
    status: pending
  - id: step4-frontend
    content: "Step 4: 프론트엔드 MVP (TileViewer, MaskCanvas, GridOverlay, undo/redo)"
    status: pending
  - id: step5-export
    content: "Step 5: Export + U-Net dataloader smoke test"
    status: pending
  - id: step6-full
    content: "Step 6: Phase 3~5 워크플로 확장 (brush, 검수 큐, 학습 연동)"
    status: pending
isProject: false
---

# 개발 순서 계획 (yard-mask-studio)

## 현재 상태

레포에 `.env.example`, `.gitignore`, `README.md`, `labeling-tool-plan-v3.md`만 존재. 코드 없음.

---

## 개발 순서 개요

```
Step 0 → Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → Step 6
  환경       기준       백엔드      CLI        프론트      Export    검증/학습
  구성       정립       핵심       검증        MVP        연동
```

---

## Step 0. 프로젝트 기반 구성

**소요: 반나절**

- `pyproject.toml` 생성 (uv 기반, FastAPI / rasterio / pydantic-settings / torch 의존성)
- `frontend/package.json` 생성 (pnpm 기반, Vite + React + TS + Konva)
- 디렉토리 골격 생성:
  ```
  backend/
    app/
      core/          # config_schema, config_store, db, config, tenant
      tiling/        # raster_source, coordinate_utils, tile_generator, tile_index
      grid/          # grid_calculator
      sam/           # sam_predictor, prompt_handler
      annotation/    # mask_service
      dataset/       # dataset_exporter, config_snapshot, split_generator, validator
      api/           # routes, schemas
    tests/
    scripts/
  frontend/
  config/
  data/
    source/          # 원본 GeoTIFF
    datasets/        # 생성된 타일·mask
    exports/         # U-Net 학습용 export 결과
  models/            # SAM 체크포인트
  docs/
  ```
- `.env` 작성 (`.env.example` 기반: `DATABASE_URL`, `SAM_CHECKPOINT_PATH`, `LABELING_CONFIG_PATH`)
- `.gitignore`에 `data/`, `models/`, `.env` 추가 확인

**완료 기준**:
- `uv run python -c "import fastapi, rasterio, torch"` 오류 없음
- `pnpm install` 성공
- `pnpm build` 또는 `pnpm typecheck` 성공

---

## Step 1. 기준 정립 (Phase 0)

**소요: 1주**  
**의존**: Step 0 완료

**순서**:
1. `config/labeling.dev.yaml` — 설정 시드 파일 (tile_size·overlap·grid·GSD·SAM·classes)
2. `backend/app/core/config_schema.py` — `LabelingConfig` pydantic 스키마 (TilingConfig, GeoConfig, GridConfig, SamConfig, ClassesConfig)
3. `docs/dataset_spec.md` — 디렉토리 구조·mask PNG 규칙·메타데이터 스키마·타일 상태 정의
4. `docs/api_spec.yaml` — OpenAPI 3.0 전체 엔드포인트 초안 (§10 기반)
5. `docs/labeling_guide.md` — 라벨링 기준표 v0.1 초안 (occupied/ignore/non_occupied 정의 + 예시 자리표시자; 실제 정사영상 확보 후 시각 예시 20장 이상 보강)

**완료 기준**: config_schema.py를 import해 yaml을 파싱하면 LabelingConfig 객체 생성 성공; `backend/tests/test_config_schema.py`로 기본값·검증 규칙까지 확인

---

## Step 2. 백엔드 핵심 (Phase 1) — 순서 중요

**소요: 2주**  
**의존**: Step 1 완료 (config_schema.py 확정 후 진행)

### 2-1. 설정 계층 (먼저)
- `backend/app/core/db.py` — SQLite 연결, DDL (active_config·config_change_snapshots·dataset_config_snapshots·datasets·tiles·annotations 테이블; review_queue는 Step 6에서 추가)
- `backend/app/core/config_store.py` — active_config CRUD + 스냅샷 + YAML 시드 import
- `backend/app/core/config.py` — `get_startup_config()` (DB → YAML 시드 순)
- `backend/app/core/tenant.py` — tenant_id 검증

### 2-2. 타일링
- `backend/app/tiling/raster_source.py` — `RasterSource` 추상 인터페이스 + GeoTIFF 구현 (rasterio)
- `backend/app/tiling/coordinate_utils.py` — GSD 계산, 픽셀↔미터 변환
- `backend/app/tiling/tile_generator.py` — TilingConfig 주입형 타일 생성 (windowed read·edge padding)
- `backend/app/tiling/tile_index.py` — SQLite 타일 인덱스 CRUD

### 2-3. 그리드
- `backend/app/grid/grid_calculator.py` — grid_size_meters → 픽셀 크기 계산

### 2-4. SAM 추론
- `backend/app/sam/sam_predictor.py` — SAM 2.1 image predictor 래핑 (`SegmentationBackend` 프로토콜)
- `backend/app/sam/prompt_handler.py` — point/box prompt 변환

### 2-5. Annotation
- `backend/app/annotation/mask_service.py` — class index mask PNG 저장·로드·RLE 변환

### 2-6. API + 테스트
- `backend/app/api/schemas.py` — pydantic 요청/응답 모델 (api_spec.yaml 기반)
- `backend/app/api/routes.py` — FastAPI 라우트 연결 — config / dataset / tile / SAM / annotation 엔드포인트 (export API는 Step 5에서 구현)
- `backend/tests/test_config_store.py`
- `backend/tests/test_tile_generator.py` (tile_size=512·1024·2048)
- `backend/tests/test_grid_calculator.py` (grid_size_meters=15·20)
- `backend/tests/test_coordinate_utils.py` — GSD 계산·픽셀↔미터 변환 수치 검증 (그리드·후처리 계산의 핵심)
- `backend/tests/test_mask_service.py` — class index mask PNG 저장·로드·RLE 왕복 검증 (U-Net 학습 데이터 품질에 직결)
- `backend/tests/test_sam_predictor.py` — mock backend로 point/box prompt 입출력 구조 검증 (SAM 체크포인트 불필요)
- `backend/tests/test_api_routes.py` — FastAPI TestClient로 경로·요청/응답 스키마 정합성 검증

**완료 기준**: 각 모듈 단위 테스트 통과

---

## Step 3. CLI 검증 (Phase 1 완료 기준)

**소요: 2일**  
**의존**: Step 2 전체

- `backend/scripts/make_test_geotiff.py` — 합성 RGB GeoTIFF 생성 (CRS·transform 포함, measured_gsd_x/y_cm 계산 테스트, windowed read 테스트용; 실제 정사영상 없이도 타일링/GSD/메타데이터 검증 가능)
- `backend/scripts/cli.py` 작성
- 실제 GeoTIFF 또는 `make_test_geotiff.py` 생성 합성 이미지로 엔드-투-엔드 검증:
  1. GeoTIFF 로드 → 타일 생성 (tile_size=512, 1024)
  2. SAM 추론 → mask 후보 생성
  3. class index mask PNG 저장
  4. 메타데이터 JSON에 `measured_gsd_x_cm`, `gsd_source`, `dataset_config_snapshot_id` 포함 확인

**완료 기준**: CLI만으로 타일 1장 SAM 추론 → class index mask PNG 저장 성공, `tile_size=512`와 `tile_size=1024` 각각 동작

---

## Step 4. 프론트엔드 MVP (Phase 2)

**소요: 2주**  
**의존**: Step 3 완료 (API가 안정적으로 동작한 후 시작)

**순서**:
1. Vite + React + TypeScript + Konva 프로젝트 초기화 (`frontend/`)
2. `frontend/src/api/client.ts` — axios + zod, OpenAPI 스펙 기반
3. `frontend/src/stores/configStore.ts` — 서버 설정 동기화
4. `frontend/src/stores/annotationStore.ts` — mask 상태 + undo/redo 20단계 히스토리
5. `frontend/src/components/TileViewer.tsx` — Konva zoom/pan
6. `frontend/src/components/MaskCanvas.tsx` — mask overlay (반투명 컬러)
7. `frontend/src/components/GridOverlay.tsx` — 그리드 오버레이 (설정 기반)
8. `frontend/src/components/ClassPanel.tsx` — occupied/ignore 토글
9. SAM point/box prompt 입력 UI
10. save/load 버튼 (백엔드 연결)

**완료 기준**: GUI로 타일 1장 라벨링 → 저장 → 재로드, 그리드 크기 변경 시 즉시 반영, undo/redo 20단계 동작

---

## Step 5. Export + U-Net smoke test (MVP 완료 기준)

**소요: 3~5일** (train/val/test split 형식, ignore index 255 처리, mask dtype 검증, 이미지·mask 크기 불일치, dataloader batch 구성, grayscale mask 로딩 방식 등 변수 고려)

- `backend/app/dataset/dataset_exporter.py` — class index mask PNG export
- `backend/app/dataset/config_snapshot.py` — export 시 설정 스냅샷 저장
- `backend/app/dataset/split_generator.py` — train/val/test 분할
- `backend/app/dataset/validator.py` — image/mask 1:1 매칭 검증

### Step 5-A. CLI 생성 샘플 mask로 export + dataloader smoke test
**의존**: Step 3 완료  
`make_test_geotiff.py` 또는 CLI로 생성한 mask PNG를 사용해 export 파이프라인과 U-Net dataloader를 먼저 검증한다. 프론트엔드 완료 전에도 학습 데이터 포맷 검증을 끝낼 수 있다.

### Step 5-B. GUI 저장 결과로 export + dataloader smoke test
**의존**: Step 4 완료  
GUI로 라벨링·저장한 데이터를 export해 U-Net dataloader가 동일하게 동작하는지 검증한다.

**완료 기준**: export 후 U-Net dataloader가 에러 없이 동작, ignore index 255가 dataloader에서 정상 제외 처리됨, config_snapshot.yaml 함께 저장

---

## Step 6. 워크플로 확장 (Phase 3~5, Full v0.3)

**의존**: MVP(Step 0~5) 완료 후

- Phase 3: TileNavigator (타일 목록·상태 필터) + brush 편집 + 검수 큐
- Phase 4: export API 정식화 + 설정 영향도 분석 API
- Phase 5: 100~300장 라벨링 → U-Net 1차 학습 → 가이드 보완

---

## 마일스톤 요약

| 마일스톤 | 내용 | 예상 시점 |
|---|---|---|
| M0 | 환경 구성 완료 | Day 1 |
| M1 | config_schema + api_spec 확정 | Week 1 |
| M2 | CLI로 SAM 추론 → mask 저장 | Week 3 |
| M3 | GUI 라벨링 → 저장 → 재로드 | Week 5 |
| MVP | export + U-Net smoke test 통과 | Week 5~6 |
| Full | 검수 큐 + 100장 라벨링 완료 | Week 10 |

---

## 핵심 제약 (개발 순서에서 지켜야 할 것)

- `config_schema.py`가 확정되기 전에 다른 모듈 코드를 작성하지 않는다 — 모든 모듈이 `LabelingConfig`를 주입받으므로 스키마가 흔들리면 전체 수정 필요
- `api_spec.yaml` 초안이 나온 후 `routes.py`와 `schemas.py`를 작성한다 (API 스펙 우선)
- 백엔드 CLI 검증(Step 3)이 완료되기 전에 프론트엔드를 시작하지 않는다
- SAM 체크포인트(`models/` 하위)는 **Step 2-4 시작 전**에 준비한다; 단, SAM predictor 단위 테스트는 checkpoint가 없을 경우 mock backend로도 실행 가능하게 작성해 CI가 모델 파일에 의존하지 않도록 한다
