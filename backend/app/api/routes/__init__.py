"""API 라우터 집약."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.routes import annotation, config, datasets, exports, review, sam, stubs, tiles, uploads

api_router = APIRouter()
api_router.include_router(config.router)
api_router.include_router(datasets.router)
api_router.include_router(uploads.router)
api_router.include_router(tiles.router)
api_router.include_router(sam.router)
api_router.include_router(annotation.router)
api_router.include_router(exports.router)
api_router.include_router(review.router)
api_router.include_router(stubs.router)
