"""앱 전역 logging 설정 — APP_ENV=dev 이면 DEBUG."""

from __future__ import annotations

import logging
import sys


def configure_logging(app_env: str) -> None:
    level = logging.DEBUG if app_env == "dev" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    if app_env != "dev":
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
