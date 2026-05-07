"""환경 변수(.env) 로드 — 경로·비밀. LabelingConfig 와는 분리."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./data/labeling.db")
    sam_checkpoint_path: str | None = None
    sam_model_cfg: str | None = None
    app_env: str = "dev"
    labeling_config_path: str = Field(default="config/labeling.dev.yaml")
    default_tenant_id: str = "default"

    def resolved_labeling_config_path(self, cwd: Path | None = None) -> Path:
        p = Path(self.labeling_config_path)
        if p.is_absolute():
            return p
        base = cwd or Path.cwd()
        return (base / p).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
