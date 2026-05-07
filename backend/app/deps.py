"""FastAPI 의존성: DB 세션, 설정."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session


def get_db(request: Request) -> Generator[Session, None, None]:
    engine = request.app.state.engine
    with Session(engine) as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
