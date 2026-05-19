from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.api.routes import api_router
from backend.app.core.config import ensure_active_config
from backend.app.core.db import init_db
from backend.app.core.logging_config import configure_logging
from backend.app.core.settings import get_settings
from backend.app.sam.sam_predictor import LazySam2Predictor


def _ensure_sqlite_dir(database_url: str) -> None:
    if database_url.startswith("sqlite:///"):
        raw = database_url.removeprefix("sqlite:///")
        p = Path(raw)
        if not p.is_absolute():
            p = Path.cwd() / p
        if p.parent != Path.cwd():
            p.parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.app_env)
    _ensure_sqlite_dir(settings.database_url)
    engine = create_engine(settings.database_url, future=True)
    init_db(engine)
    repo_root = Path(__file__).resolve().parents[2]
    with Session(engine) as session:
        cfg = ensure_active_config(session, settings, cwd=repo_root)
    app.state.engine = engine
    app.state.settings = settings
    app.state.labeling_config = cfg
    app.state.repo_root = repo_root
    app.state.sam_predictor = LazySam2Predictor(
        settings.sam_checkpoint_path,
        settings.sam_model_cfg,
        embedding_cache_max=settings.sam_embedding_cache_max,
    )
    yield
    engine.dispose()


app = FastAPI(
    title="yard-mask-studio",
    lifespan=lifespan,
    description="""
**U-Net 학습용 라벨링** 백엔드 API.

- **원본 GeoTIFF** 경로: `data/source/{tenant_id}/raw_geotiff/{파일명}` (파일명만 API에 전달).
- **워크플로**: 데이터셋 생성 → 타일 생성(`tiles/generate`) → 타일 목록/이미지/메타 → SAM 예측(선택) → annotation 저장.
- **테넌트**: `tenant_id`는 서버 `.env`의 `DEFAULT_TENANT_ID`와 같아야 합니다.
""",
    openapi_tags=[
        {
            "name": "config",
            "description": "SQLite `active_config` — 타일 크기·그리드·클래스·SAM 설정 등. 서버 기동 시 YAML 시드로 채워질 수 있음.",
        },
        {
            "name": "datasets",
            "description": "데이터셋 등록 및 GeoTIFF로부터 타일 PNG 일괄 생성.",
        },
        {
            "name": "uploads",
            "description": "GeoTIFF 원본 파일 업로드 및 서버 `raw_geotiff/` 목록 조회.",
        },
        {
            "name": "tiles",
            "description": "생성된 타일 목록, PNG 이미지, 메타데이터(JSON), 상태 변경.",
        },
        {
            "name": "sam",
            "description": "타일 이미지 + 프롬프트 기반 SAM2 세그멘테이션 후보(RLE). 체크포인트·환경에 따라 503 가능.",
        },
        {
            "name": "annotation",
            "description": "확정 클래스 마스크(RLE) 저장·조회·삭제 및 `masks/{tile_id}.png` 동기화.",
        },
        {
            "name": "exports",
            "description": "U-Net 학습용 export 생성 결과 조회 및 ZIP 다운로드.",
        },
        {
            "name": "review",
            "description": "검수 큐 조회 및 타일 단위 승인/거부.",
        },
        {
            "name": "stubs",
            "description": "예약용 빈 라우터(향후 확장).",
        },
    ],
)
app.include_router(api_router, prefix="/api")
