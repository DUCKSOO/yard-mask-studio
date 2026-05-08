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

## SAM 모델 추가 방법

허용 **백본 variant** 는 코드·설정·OpenAPI에서 동일한 목록으로 관리한다: `hiera_base` (시드·`.env.example` 기본, VRAM 부담 적음), `hiera_large` (고성능·고메모리).

1. **체크포인트**를 레포의 `models/` 에 둔다 (`models/` 는 `.gitignore` 대상).  
   - 수동: [facebookresearch/sam2](https://github.com/facebookresearch/sam2) 의 `checkpoints/download_ckpts.sh` 와 동일한 Meta CDN URL에서 받는다.  
   - 스크립트: 저장소 루트에서 `uv run python scripts/download_sam_checkpoint.py --variant hiera_base`  
     (선택) `--with-config` 로 같은 디렉터리에 `sam2.1_hiera_b+.yaml` 등 설정 YAML도 받을 수 있다. `hiera_large` 는 `--variant hiera_large` → `sam2.1_hiera_large.pt` + `sam2.1_hiera_l.yaml` 에 대응한다.
2. `.env` 의 `SAM_CHECKPOINT_PATH` 를 그 `.pt` 파일의 **절대 경로**로 맞춘다. `SAM_MODEL_CFG` 는 사용 중인 variant에 맞게 둔다 (예: large → `sam2.1_hiera_l.yaml`, base → `sam2.1_hiera_b+.yaml`).
3. 새 아키텍처 이름을 쓰려면 다음을 **한 세트로** 갱신한다.  
   - [`backend/app/core/config_schema.py`](backend/app/core/config_schema.py) — `SamModelVariant` / `SamConfig.model_variant` 의 `Literal` 에 값 추가 (모듈 상단 독스트링 절차 참고).  
   - [`config/labeling.dev.yaml`](config/labeling.dev.yaml), [`config/labeling.prod.yaml`](config/labeling.prod.yaml) — `sam.model_variant` 주석·값.  
   - [`docs/api_spec.yaml`](docs/api_spec.yaml) — `components/schemas/SamModelVariant` 의 `enum`.  
4. `uv run pytest` 로 설정 스키마 테스트가 통과하는지 확인한다.

---

## 사전 요구 사항

| 도구 | 용도 |
|------|------|
| [uv](https://docs.astral.sh/uv/) | Python 3.11 고정, 가상환경 생성·의존성 설치 |
| [pnpm](https://pnpm.io/) | 프론트엔드 패키지 설치 및 개발 서버 |

Python 버전은 **별도로 설치할 필요 없음**. `uv sync`가 프로젝트에 맞는 CPython 3.11을 받아 `.venv`에 둡니다.

---

## Python 가상환경 (uv)

1. 저장소 루트에서 한 번만 의존성을 맞춘다.

   ```bash
   uv sync --group dev
   ```

2. 위 명령이 프로젝트 루트에 **`.venv`** 디렉터리를 만들고, `pyproject.toml` 기준으로 패키지를 설치한다. (`.venv`는 `.gitignore`에 포함됨.)

3. **권장**: 가상환경을 셸에서 `activate` 하지 않고, 루트에서 `uv run <명령>`으로 실행한다. **`uv run`은 프로젝트의 `.venv` 안의 Python·설치된 패키지로 그 명령을 구동**한다. 즉 “시스템 전역 Python”이 아니라 **`uv sync`로 만든 가상환경과 동일한 환경**이다. (매번 활성화만 생략하는 방식.)

4. **선택**: IDE 터미널이나 스크립트에서 가상환경을 활성화해 쓰려면 다음과 같다.

   - **Windows (PowerShell)**  
     `.\.venv\Scripts\Activate.ps1`
   - **Windows (cmd)**  
     `.\.venv\Scripts\activate.bat`
   - **macOS / Linux**  
     `source .venv/bin/activate`

   활성화 후에는 `python`, `pytest`, `uvicorn` 등을 일반 명령처럼 실행할 수 있다. (비활성화: `deactivate`)

---

## 실행 방법

### 1. 환경 변수

```bash
cp .env.example .env
```

`.env`에서 최소한 `SAM_CHECKPOINT_PATH`(로컬 절대 경로), 필요 시 `DATABASE_URL`·`LABELING_CONFIG_PATH`를 맞춘다. `.env`는 git에 올리지 않는다.

### 2. 백엔드 (FastAPI)

저장소 **루트**에서:

```bash
uv sync --group dev
uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

- API 문서: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 위 `uv run uvicorn ...` 는 **`.venv`에 설치된 `uvicorn`** 으로 서버가 뜬다. 전역 Python이 아니다.
- 가상환경을 수동으로 활성화한 뒤에는 같은 디렉터리에서 `uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000` 만 실행해도 동일하다.

**백엔드 파이프라인 스모크 (Step 3)** — 합성 GeoTIFF로 타일 생성·메타데이터·(stub) SAM·mask PNG까지 확인할 때 (저장소 루트에서):

```bash
uv run python -m backend.scripts.cli make-geotiff data/source/default/raw_geotiff/synthetic.tif
uv run python -m backend.scripts.cli e2e --synthetic --tile-size 512 --dataset-id step3_demo
```

SAM 본추론은 미연동이므로 기본은 `StubSegmentationBackend` 이다. 시각적 마스크가 필요하면 `e2e` 에 `--disk-mask` 를 붙인다. 별도 DB로 돌리려면 `--database-url sqlite:///./data/step3_cli.db` 처럼 지정한다. 같은 `--dataset-id` 로 재실행하면 데이터셋 중복 오류가 나므로 ID를 바꾸거나 DB를 비운다.

### 3. 프론트엔드 (Vite)

별도 터미널에서:

```bash
cd frontend
pnpm install
pnpm dev
```

- 개발 서버 기본 주소: [http://localhost:5173](http://localhost:5173)
- **`pnpm dev`는 `/api`를 `http://127.0.0.1:8000`으로 프록시**하므로, 위 백엔드를 먼저 띄운 뒤 접속한다.
- 기본 테넌트·데이터셋은 `default` / `step3_e2e` (Step 3 CLI로 만든 예시). 바꾸려면 사이드바 입력 또는 `.env`에 `VITE_TENANT_ID`, `VITE_DATASET_ID` 를 둔다.
- 프록시 없이 빌드 미리보기 등에서 API를 직접 부를 때는 `VITE_API_BASE_URL=http://127.0.0.1:8000` 을 설정한다 (백엔드에 CORS가 없으면 개발 시 프록시 사용 권장).

### 4. 프로덕션 빌드 (프론트)

```bash
cd frontend
pnpm install
pnpm run build
```

산출물은 `frontend/dist/` 에 생성된다.

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
│       ├── cli.py                  # Step 3 e2e (타일·stub SAM·mask)
│       └── make_test_geotiff.py    # 합성 GeoTIFF
│
├── frontend/                       # React + TypeScript
│   ├── src/
│   │   ├── components/
│   │   │   ├── TileViewer.tsx      # 타일 이미지 (Konva)
│   │   │   ├── MaskCanvas.tsx      # mask 오버레이·브러시
│   │   │   ├── ClassPanel.tsx      # 클래스 선택
│   │   │   ├── ToolBar.tsx         # 도구·SAM 실행
│   │   │   └── GridOverlay.tsx     # 그리드 시각화
│   │   ├── api/
│   │   │   └── client.ts           # axios + zod API 클라이언트
│   │   └── stores/
│   │       ├── annotationStore.tsx # mask + undo/redo (20)
│   │       └── configStore.tsx     # 서버 설정 동기화
│   ├── package.json
│   └── vite.config.ts
│
├── config/
│   ├── labeling.dev.yaml           # 개발 시드 (LABELING_CONFIG_PATH 기본값)
│   └── labeling.prod.yaml          # 운영 시드 (APP_ENV=prod 등에서 지정)
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
│   ├── assets/                     # 라벨링 가이드 시각 예시 (추가 예정)
│   ├── labeling_guide.md           # 라벨링 기준표
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
| 운영 고정값 (시드) | `config/labeling.dev.yaml`, `config/labeling.prod.yaml` | 첫 실행 시 DB로 import. 이후 DB `active_config` 우선 (`.env`의 `LABELING_CONFIG_PATH`로 파일 선택) |
| 런타임 변경 가능 | SQLite `active_config` | `POST /api/config`로 즉시 반영. 변경 전 값은 스냅샷 보존 |

---

## Step 0 완료 검증

```bash
# Python (FastAPI, rasterio, torch 임포트)
uv sync --group dev
uv run python -c "import fastapi, rasterio, torch"
uv run pytest

# 프론트엔드 빌드
cd frontend
pnpm install
pnpm run build
pnpm run test
```

---

## 빠른 시작 (요약)

자세한 설명은 위 **Python 가상환경 (uv)** 절과 **실행 방법** 절을 참고한다.

```bash
cp .env.example .env   # 후에 SAM_CHECKPOINT_PATH 등 수정

uv sync --group dev
uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# 다른 터미널
cd frontend && pnpm install && pnpm dev
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

| 문서 | 대상 | 내용 |
|------|------|------|
| [사용자 가이드](./docs/user_guide.md) | 라벨러·검수자 | 화면 구성, 도구 사용법, 단축키, 작업 순서 |
| [라벨링 기준표](./docs/labeling_guide.md) | 라벨러·검수자 | 클래스 정의, occupied 판정 기준, 품질 기준 |
| [설정 변경 가이드](./docs/config_guide.md) | 관리자 | tile_size·GSD 등 런타임 설정 변경 방법 |
| [데이터셋 명세](./docs/dataset_spec.md) | 개발자·MLOps | export 결과물 디렉터리·mask 포맷 |
| [API 스펙](./docs/api_spec.yaml) | 개발자 | OpenAPI 엔드포인트 명세 |
| [설계 계획서](./labeling-tool-plan-v3.md) | 개발자 | 전체 아키텍처·단계별 설계 |
