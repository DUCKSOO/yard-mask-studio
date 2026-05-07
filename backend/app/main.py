from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.api.routes import api_router
from backend.app.core.config import ensure_active_config
from backend.app.core.db import init_db
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
    app.state.sam_predictor = LazySam2Predictor(settings.sam_checkpoint_path, settings.sam_model_cfg)
    yield
    engine.dispose()


app = FastAPI(title="yard-mask-studio", lifespan=lifespan)
app.include_router(api_router, prefix="/api")
