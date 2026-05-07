# yard-mask-studio

드론 정사영상에서 **U-Net 학습용 점유/비점유 세그멘테이션 라벨**을 생성하는 내부 라벨링 도구.  
SAM 2.1로 mask 후보를 제안하고, 작업자가 확정한 뒤 class index mask PNG로 저장한다.

> AI-02 영역 추출 → **라벨링(본 도구)** → AI-03 데이터셋 학습

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| 백엔드 | Python 3.11, FastAPI, SQLite, rasterio/GDAL |
| 설정 관리 | pydantic-settings, YAML 시드 → SQLite `active_config` (런타임 변경) |
| AI 추론 | PyTorch 2.x, SAM 2.1 (image predictor mode) |
| 프론트엔드 | React + TypeScript, Vite, Konva.js |
| 패키지 관리 | uv (Python), pnpm (Node) |
| 테스트 | pytest, vitest |

---

## 레포 구조

```
yard-mask-studio/
│
├── backend/                        # FastAPI 백엔드
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py           # 설정 로더 (시작 시 DB → YAML 시드 순)
│   │   │   ├── config_schema.py    # LabelingConfig pydantic 스키마
│   │   │   ├── config_store.py     # active_config CRUD + 스냅샷
│   │   │   ├── db.py               # SQLite 연결 팩토리
│   │   │   └── tenant.py           # 테넌트 격리
│   │   │
│   │   ├── tiling/
│   │   │   ├── raster_source.py    # 입력 래스터 추상화 (1차: GeoTIFF)
│   │   │   ├── tile_generator.py   # RasterSource → 타일
│   │   │   ├── tile_index.py       # 타일 인덱스 (SQLite)
│   │   │   └── coordinate_utils.py # 픽셀↔미터 변환
│   │   │
│   │   ├── grid/
│   │   │   ├── grid_calculator.py  # 그리드 픽셀 크기 계산
│   │   │   └── grid_overlay.py     # 추론 결과 그리드 매핑
│   │   │
│   │   ├── sam/
│   │   │   ├── sam_predictor.py    # SAM 추론 (SegmentationBackend 프로토콜)
│   │   │   └── prompt_handler.py   # prompt 변환·검증
│   │   │
│   │   ├── annotation/
│   │   │   ├── mask_service.py     # mask 저장·편집
│   │   │   ├── review_queue.py     # 검수 큐
│   │   │   └── migration.py        # 스키마 변경 시 라벨 마이그레이션
│   │   │
│   │   ├── dataset/
│   │   │   ├── dataset_exporter.py # U-Net export (포맷 플러그인 구조)
│   │   │   ├── split_generator.py  # train/val/test 분할
│   │   │   ├── validator.py        # 무결성 검증
│   │   │   └── config_snapshot.py  # export 시 설정 스냅샷 저장
│   │   │
│   │   └── api/
│   │       ├── routes.py
│   │       └── schemas.py          # pydantic 요청/응답 스키마
│   │
│   ├── tests/
│   └── scripts/
│       └── cli.py                  # CLI 검증 도구
│
├── frontend/                       # React + TypeScript
│   ├── src/
│   │   ├── components/
│   │   │   ├── TileViewer.tsx      # 타일 zoom/pan (Konva)
│   │   │   ├── MaskCanvas.tsx      # mask 편집 캔버스
│   │   │   ├── ClassPanel.tsx      # occupied/ignore 토글
│   │   │   ├── ToolBar.tsx
│   │   │   ├── TileNavigator.tsx   # 타일 목록·상태 필터
│   │   │   ├── ReviewPanel.tsx     # 검수 승인/거부
│   │   │   └── GridOverlay.tsx     # 그리드 시각화
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
├── data/                           # git에서 제외 (.gitignore)
│   ├── source/                     # 원본 GeoTIFF
│   ├── tiles/                      # 생성된 타일
│   ├── annotations/                # 라벨링 결과
│   └── exports/                    # U-Net 학습용 export
│
├── models/                         # git에서 제외
│   └── (SAM 체크포인트)
│
├── docs/
│   ├── labeling_guide.md           # 라벨링 기준표 (시각 예시 포함)
│   ├── api_spec.yaml               # OpenAPI 3.0 스펙
│   ├── dataset_spec.md             # 데이터셋 구조·export 규칙
│   └── config_guide.md             # 설정 변경 가이드
│
├── .env.example                    # 환경변수 템플릿
├── .gitignore
├── pyproject.toml                  # uv 기반 Python 의존성
├── labeling-tool-plan-v3.md        # 설계 계획서
└── README.md
```

---

## 설정 계층

| 계층 | 위치 | 설명 |
|---|---|---|
| 환경 의존 (비밀·경로) | `.env` | DB URL, 체크포인트 절대경로 등. 서버 시작 시 고정 |
| 운영 고정값 (시드) | `config/labeling.yaml` | 첫 실행 시 DB로 import. 이후 DB 우선 |
| 런타임 변경 가능 | SQLite `active_config` | `POST /api/config`로 즉시 반영. 변경 전 값은 스냅샷 보존 |

---

## 빠른 시작

```bash
# 환경변수 설정
cp .env.example .env
# 편집: DATABASE_URL, SAM_CHECKPOINT_PATH

# Python 의존성 (uv)
uv sync

# 서버 실행
uv run uvicorn backend.app.main:app --reload

# 프론트엔드
cd frontend
pnpm install
pnpm dev
```

---

## 데이터 디렉토리 구조

```
data/
├── source/
│   └── {tenant_id}/raw_geotiff/     # 원본 GeoTIFF
├── datasets/
│   └── {tenant_id}/
│       └── {dataset_id}/
│           ├── images/              # 타일 PNG
│           ├── masks/               # class index mask PNG (0: non_occupied, 1: occupied, 255: ignore)
│           ├── metadata/            # 타일별 JSON (geo_transform, measured_gsd_x/y_cm 등)
│           ├── splits/              # train.json / val.json / test.json
│           ├── config_snapshot.yaml # 데이터셋 생성 시점의 불변 설정
│           ├── classes.json
│           └── dataset_manifest.json
└── exports/
    └── {tenant_id}/
        └── {dataset_id}/
            └── {export_id}/         # U-Net export 결과물
```

---

## 관련 문서

- [설계 계획서](./labeling-tool-plan-v3.md)
- [라벨링 기준표](./docs/labeling_guide.md) _(Phase 0에서 작성)_
- [API 스펙](./docs/api_spec.yaml) _(Phase 0에서 작성)_
- [데이터셋 명세](./docs/dataset_spec.md) _(Phase 0에서 작성)_
- [설정 변경 가이드](./docs/config_guide.md) _(Phase 0에서 작성)_
