"""공통 pytest fixture."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.db import init_db
from backend.app.core.settings import clear_settings_cache

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db_engine(tmp_path: Path):
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url, future=True)
    init_db(engine)
    return engine


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """임시 SQLite + 레포 루트 cwd 로 FastAPI TestClient."""
    monkeypatch.chdir(REPO_ROOT)
    db_url = f"sqlite:///{(tmp_path / 'api.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("LABELING_CONFIG_PATH", "config/labeling.dev.yaml")
    monkeypatch.setenv("DEFAULT_TENANT_ID", "default")
    clear_settings_cache()
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.app.sam.sam_predictor import StubSegmentationBackend

    with TestClient(app) as client:
        app.state.sam_predictor = StubSegmentationBackend()
        yield client
    clear_settings_cache()
