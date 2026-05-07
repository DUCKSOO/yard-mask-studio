"""API 라우터 집약."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.routes import annotation, config, datasets, sam, stubs, tiles

api_router = APIRouter()
api_router.include_router(config.router)
api_router.include_router(datasets.router)
api_router.include_router(tiles.router)
api_router.include_router(sam.router)
api_router.include_router(annotation.router)
api_router.include_router(stubs.router)
