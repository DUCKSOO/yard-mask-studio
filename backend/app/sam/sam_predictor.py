"""세그멘테이션 백엔드 프로토콜 및 SAM2 지연 로딩 래퍼."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np
import torch

from backend.app.sam.prompt_handler import BoxPrompt, PointPrompt

logger = logging.getLogger(__name__)


class SamUnavailableError(RuntimeError):
    """체크포인트 없음·설정 오류·SAM 로드 실패 등."""


@runtime_checkable
class SegmentationBackend(Protocol):
    def predict(
        self,
        image_hwc: np.ndarray,
        prompts: list[Any],
        *,
        multimask_output: bool = True,
        max_candidates: int = 3,
    ) -> list[np.ndarray]:
        """image_hwc: uint8 or float HxWxC. 반환: 각 후보 mask HxW (bool 또는 uint8)."""
        ...


class StubSegmentationBackend:
    """테스트용 — 빈 마스크 리스트."""

    def predict(
        self,
        image_hwc: np.ndarray,
        prompts: list[Any],
        *,
        multimask_output: bool = True,
        max_candidates: int = 3,
    ) -> list[np.ndarray]:
        h, w = image_hwc.shape[:2]
        n = len(prompts) if prompts else 1
        return [np.zeros((h, w), dtype=np.float32) for _ in range(min(n, max(1, max_candidates)))]


def _resolve_sam2_config_name(model_cfg: str | None) -> str:
    """Hydra config_name for sam2.build_sam.build_sam2 (패키지 내 configs/ 기준)."""
    if not model_cfg or not str(model_cfg).strip():
        raise SamUnavailableError("SAM_MODEL_CFG missing or empty")
    name = str(model_cfg).strip().replace("\\", "/")
    if name.startswith("configs/"):
        return name
    if "/" in name:
        return name
    if name.startswith("sam2.1_"):
        return f"configs/sam2.1/{name}"
    if name.startswith("sam2_"):
        return f"configs/sam2/{name}"
    return f"configs/sam2.1/{name}"


def _prompts_to_sam_inputs(
    prompts: list[Any],
) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]:
    """PointPrompt / BoxPrompt 리스트 → SAM2ImagePredictor.predict 인자."""
    coords: list[list[float]] = []
    labels: list[int] = []
    box_arr: np.ndarray | None = None

    for p in prompts:
        if isinstance(p, PointPrompt):
            coords.append([float(p.x), float(p.y)])
            labels.append(1 if p.label == "positive" else 0)
        elif isinstance(p, BoxPrompt):
            box_arr = np.array([p.x1, p.y1, p.x2, p.y2], dtype=np.float32)

    point_coords = np.array(coords, dtype=np.float32) if coords else None
    point_labels = np.array(labels, dtype=np.int32) if labels else None
    return point_coords, point_labels, box_arr


class LazySam2Predictor:
    """SAM 2 체크포인트가 유효할 때 실추론; 없으면 SamUnavailableError."""

    def __init__(self, checkpoint_path: str | None, model_cfg: str | None) -> None:
        self._checkpoint_path = checkpoint_path
        self._model_cfg = model_cfg
        self._predictor = None
        self._lock = threading.Lock()
        self._device: str = "cpu"

        if checkpoint_path and Path(checkpoint_path).is_file():
            logger.info(
                "LazySam2Predictor checkpoint present path=%s cfg=%s",
                checkpoint_path,
                model_cfg,
            )
        else:
            logger.warning(
                "LazySam2Predictor no valid checkpoint (path=%s exists=%s)",
                checkpoint_path,
                bool(checkpoint_path and Path(checkpoint_path).is_file()),
            )

    def _ensure_predictor(self) -> None:
        if self._predictor is not None:
            return
        if not self._checkpoint_path or not Path(self._checkpoint_path).is_file():
            raise SamUnavailableError("SAM_CHECKPOINT_PATH missing or file not found")

        try:
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor
        except ImportError as e:
            raise SamUnavailableError(f"sam2 package import failed: {e}") from e

        cfg_name = _resolve_sam2_config_name(self._model_cfg)
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(
            "Loading SAM2 model cfg=%s ckpt=%s device=%s",
            cfg_name,
            self._checkpoint_path,
            self._device,
        )
        try:
            sam_model = build_sam2(
                config_file=cfg_name,
                ckpt_path=self._checkpoint_path,
                device=self._device,
                mode="eval",
            )
        except Exception as e:
            logger.exception("build_sam2 failed")
            raise SamUnavailableError(f"SAM2 model load failed: {e}") from e

        self._predictor = SAM2ImagePredictor(sam_model)
        logger.info("SAM2ImagePredictor ready")

    def predict(
        self,
        image_hwc: np.ndarray,
        prompts: list[Any],
        *,
        multimask_output: bool = True,
        max_candidates: int = 3,
    ) -> list[np.ndarray]:
        if not self._checkpoint_path or not Path(self._checkpoint_path).is_file():
            raise SamUnavailableError("SAM_CHECKPOINT_PATH missing or file not found")

        if not prompts:
            raise ValueError("at least one prompt is required")

        point_coords, point_labels, box = _prompts_to_sam_inputs(prompts)
        if point_coords is None and box is None:
            raise ValueError("no valid point or box prompts")

        with self._lock:
            self._ensure_predictor()
            assert self._predictor is not None

            try:
                self._predictor.set_image(image_hwc)
                masks_np, iou_np, _low = self._predictor.predict(
                    point_coords=point_coords,
                    point_labels=point_labels,
                    box=box,
                    multimask_output=multimask_output,
                    return_logits=False,
                    normalize_coords=True,
                )
            except Exception as e:
                logger.exception("SAM2 predict failed")
                raise SamUnavailableError(f"SAM2 inference failed: {e}") from e

        # masks_np: C x H x W (bool)
        if masks_np.ndim != 3:
            raise SamUnavailableError(f"unexpected mask shape {masks_np.shape}")

        order = np.argsort(-iou_np)
        masks_np = masks_np[order]

        k = max(1, min(int(max_candidates), masks_np.shape[0]))
        out: list[np.ndarray] = []
        for i in range(k):
            m = masks_np[i]
            out.append(m.astype(np.uint8, copy=False))

        return out
