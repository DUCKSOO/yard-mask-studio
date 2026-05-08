"""세그멘테이션 백엔드 프로토콜 및 SAM2 지연 로딩 래퍼(플레이스홀더)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np

logger = logging.getLogger(__name__)


class SamUnavailableError(RuntimeError):
    """체크포인트 없음 또는 로드 미구현."""


@runtime_checkable
class SegmentationBackend(Protocol):
    def predict(self, image_hwc: np.ndarray, prompts: list[Any]) -> list[np.ndarray]:
        """image_hwc: uint8 or float HxWxC. 반환: 각 후보 mask HxW float/bool."""
        ...


class StubSegmentationBackend:
    """테스트용 — 빈 마스크 리스트."""

    def predict(self, image_hwc: np.ndarray, prompts: list[Any]) -> list[np.ndarray]:
        h, w = image_hwc.shape[:2]
        return [np.zeros((h, w), dtype=np.float32) for _ in (prompts or [None])]


class LazySam2Predictor:
    """체크포인트 경로가 없거나 파일이 없으면 predict 시 SamUnavailableError."""

    def __init__(self, checkpoint_path: str | None, model_cfg: str | None) -> None:
        self._checkpoint_path = checkpoint_path
        self._model_cfg = model_cfg
        self._loaded = False
        if checkpoint_path and Path(checkpoint_path).is_file():
            logger.info("LazySam2Predictor checkpoint present path=%s cfg=%s", checkpoint_path, model_cfg)
        else:
            logger.warning(
                "LazySam2Predictor no valid checkpoint (path=%s exists=%s)",
                checkpoint_path,
                bool(checkpoint_path and Path(checkpoint_path).is_file()),
            )

    def predict(self, image_hwc: np.ndarray, prompts: list[Any]) -> list[np.ndarray]:
        if not self._checkpoint_path or not Path(self._checkpoint_path).is_file():
            raise SamUnavailableError("SAM_CHECKPOINT_PATH missing or file not found")
        # SAM 2.1 통합은 후속 작업 — 현재는 명시적 에러
        raise SamUnavailableError("SAM2 predictor not implemented; provide checkpoint after integration")
