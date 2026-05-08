"""U-Net용 세그멘테이션 DataLoader 스모크 테스트 (CPU).

사용 예:
  uv run python backend/scripts/unet_dataloader_smoke.py data/exports/default/my_ds/<export_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset


class UnetTileDataset(Dataset):
    """export 디렉터리의 splits/*.json + images + masks."""

    def __init__(self, export_dir: Path, split: str = "train") -> None:
        self.export_dir = export_dir.resolve()
        split_path = self.export_dir / "splits" / f"{split}.json"
        if not split_path.is_file():
            raise FileNotFoundError(split_path)
        self.tile_ids: list[str] = json.loads(split_path.read_text(encoding="utf-8"))
        self.images_dir = self.export_dir / "images"
        self.masks_dir = self.export_dir / "masks"

    def __len__(self) -> int:
        return len(self.tile_ids)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        tid = self.tile_ids[idx]
        img_path = self.images_dir / f"{tid}.png"
        mask_path = self.masks_dir / f"{tid}.png"
        img = np.array(Image.open(img_path).convert("RGB"), dtype=np.float32) / 255.0
        mask = np.array(Image.open(mask_path).convert("L"), dtype=np.int64)
        # NCHW
        x = torch.from_numpy(img).permute(2, 0, 1)
        y = torch.from_numpy(mask)
        return x, y


def main() -> int:
    p = argparse.ArgumentParser(description="U-Net dataloader + CrossEntropyLoss(ignore_index=255) 스모크")
    p.add_argument(
        "export_dir",
        type=Path,
        help="export 루트 (dataset_manifest.json 포함)",
    )
    p.add_argument("--split", default="train", choices=("train", "val", "test"))
    args = p.parse_args()
    root = args.export_dir
    if not (root / "dataset_manifest.json").is_file():
        print("dataset_manifest.json not found", file=sys.stderr)
        return 1

    ds = UnetTileDataset(root, split=args.split)
    if len(ds) == 0:
        print(f"split {args.split!r} is empty", file=sys.stderr)
        return 1

    batch_size = min(2, len(ds))
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False)

    # 클래스 수: occupied/non_occupied/ignore 등 — 데모로 3채널 logit (0,1,255 중 실제 클래스만 학습)
    num_classes = 3
    loss_fn = nn.CrossEntropyLoss(ignore_index=255)

    batch = next(iter(loader))
    x, target = batch
    _, _, h, w = x.shape
    logits = torch.randn(x.shape[0], num_classes, h, w)
    loss = loss_fn(logits, target)
    if torch.isnan(loss):
        print("loss is nan", file=sys.stderr)
        return 1
    print(f"ok batch={batch_size} loss={loss.item():.4f} (ignore_index=255)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
