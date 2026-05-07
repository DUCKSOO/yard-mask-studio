"""Step 3 엔드투엔드 검증: GeoTIFF → 타일 → SAM(stub) → class mask PNG.

실행 (저장소 루트, ``uv sync`` 후)::

    uv run python -m backend.scripts.cli make-geotiff data/source/default/raw_geotiff/synthetic.tif
    uv run python -m backend.scripts.cli e2e --synthetic --tile-size 512
    uv run python -m backend.scripts.cli e2e --synthetic --tile-size 1024 --dataset-id step3_1024

SAM 본추론은 아직 미연동이므로 기본 백엔드는 ``StubSegmentationBackend`` 이다.
시각적 마스크가 필요하면 ``--disk-mask`` 로 중심점 기준 원형 occupied(1) 영역을 쓴다.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.annotation import mask_service
from backend.app.core.config import ensure_active_config
from backend.app.core.config_store import save_active_config
from backend.app.core.db import init_db
from backend.app.core.settings import clear_settings_cache, get_settings
from backend.app.sam import prompt_handler
from backend.app.sam.sam_predictor import StubSegmentationBackend
from backend.app.services import dataset_service
from backend.app.tiling import tile_index

from backend.scripts.make_test_geotiff import write_synthetic_geotiff


def _resolve_labeling_config_path(repo_root: Path, p: str) -> str:
    path = Path(p)
    resolved = path if path.is_absolute() else (repo_root / path).resolve()
    return str(resolved)


def _ensure_sqlite_parent(url: str) -> None:
    if url.startswith("sqlite:///"):
        raw = url.removeprefix("sqlite:///")
        p = Path(raw)
        if not p.is_absolute():
            p = Path.cwd() / p
        if p.parent != Path.cwd():
            p.parent.mkdir(parents=True, exist_ok=True)


def cmd_make_geotiff(argv: list[str] | None = None) -> int:
    from backend.scripts import make_test_geotiff as m

    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    return m.main()


def cmd_e2e(args: argparse.Namespace) -> int:
    repo_root: Path = Path(args.repo_root).resolve()
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url
        clear_settings_cache()
    if args.labeling_config:
        os.environ["LABELING_CONFIG_PATH"] = _resolve_labeling_config_path(repo_root, args.labeling_config)
        clear_settings_cache()

    settings = get_settings()
    _ensure_sqlite_parent(settings.database_url)

    geotiff_filename = args.geotiff_name
    raw_dir = dataset_service.raw_geotiff_path(repo_root, args.tenant_id, geotiff_filename).parent

    if args.synthetic:
        raw_dir.mkdir(parents=True, exist_ok=True)
        dest = dataset_service.raw_geotiff_path(repo_root, args.tenant_id, geotiff_filename)
        write_synthetic_geotiff(
            dest,
            width=args.synthetic_width,
            height=args.synthetic_height,
            pixel_size_m=args.pixel_size_m,
        )
    else:
        user_path = Path(args.geotiff_path)
        dest = dataset_service.raw_geotiff_path(repo_root, args.tenant_id, geotiff_filename)
        if not user_path.is_file():
            print(f"GeoTIFF not found: {user_path}", file=sys.stderr)
            return 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(user_path, dest)

    engine = create_engine(settings.database_url, future=True)
    init_db(engine)

    with Session(engine) as session:
        cfg = ensure_active_config(session, settings, cwd=repo_root)
        if args.tile_size is not None:
            new_tiling = cfg.tiling.model_copy(update={"tile_size": args.tile_size})
            cfg = cfg.model_copy(update={"tiling": new_tiling})
            save_active_config(session, cfg, reason="cli_step3_tile_size")

        try:
            dataset_service.create_dataset(
                session,
                tenant_id=args.tenant_id,
                dataset_id=args.dataset_id,
                source_geotiff=geotiff_filename,
            )
        except ValueError as e:
            if "already exists" in str(e):
                print(
                    f"Dataset {args.dataset_id!r} already exists. Use --dataset-id or remove the row.",
                    file=sys.stderr,
                )
                return 1
            raise

        n = dataset_service.generate_tiles(
            session,
            repo_root,
            args.tenant_id,
            args.dataset_id,
            source_geotiff=geotiff_filename,
        )
        print(f"tiles_created={n}", file=sys.stderr)

    with Session(engine) as session:
        tiles = tile_index.list_tiles(session, args.tenant_id, args.dataset_id, limit=500)
        if not tiles:
            print("No tiles in index.", file=sys.stderr)
            return 1
        tile_id = sorted(t.tile_id for t in tiles)[0]

    img_path = dataset_service.dataset_dir(repo_root, args.tenant_id, args.dataset_id) / "images" / f"{tile_id}.png"
    meta_path = dataset_service.dataset_dir(repo_root, args.tenant_id, args.dataset_id) / "metadata" / f"{tile_id}.json"
    mask_dir = dataset_service.dataset_dir(repo_root, args.tenant_id, args.dataset_id) / "masks"
    mask_path = mask_dir / f"{tile_id}.png"

    im = Image.open(img_path).convert("RGB")
    arr = np.array(im, dtype=np.uint8)
    h, w = arr.shape[:2]
    raw_prompts = [{"type": "point", "x": w // 2, "y": h // 2, "label": "positive"}]
    prompts = prompt_handler.parse_prompts(raw_prompts, w, h)

    backend = StubSegmentationBackend()
    masks = backend.predict(arr, prompts)
    if not masks:
        print("SAM stub returned no masks.", file=sys.stderr)
        return 1
    m = np.asarray(masks[0], dtype=np.float32)

    if args.disk_mask:
        class_mask = np.zeros((h, w), dtype=np.uint8)
        if prompts and isinstance(prompts[0], prompt_handler.PointPrompt):
            py, px = np.ogrid[:h, :w]
            cy, cx = prompts[0].y, prompts[0].x
            r = max(8, min(w, h) // 8)
            class_mask[((py - cy) ** 2 + (px - cx) ** 2) <= r * r] = 1
    else:
        class_mask = np.where(m > 0.5, np.uint8(1), np.uint8(0))

    mask_service.save_mask_png(mask_path, class_mask)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    required = (
        "dataset_config_snapshot_id",
        "measured_gsd_x_cm",
        "measured_gsd_y_cm",
        "gsd_source",
        "expected_gsd_cm",
        "mask_schema_version",
    )
    missing = [k for k in required if k not in meta]
    if missing:
        print(f"metadata missing keys: {missing}", file=sys.stderr)
        return 1

    print(json.dumps({"tile_id": tile_id, "mask": str(mask_path.relative_to(repo_root)), "meta": meta_path.name}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="yard-mask-studio backend CLI")
    sub = root.add_subparsers(dest="command", required=True)

    p_mg = sub.add_parser("make-geotiff", help="Write synthetic RGB GeoTIFF (see make_test_geotiff.py)")
    p_mg.add_argument("output", type=Path)
    p_mg.add_argument("--width", type=int, default=800)
    p_mg.add_argument("--height", type=int, default=600)
    p_mg.add_argument("--pixel-size-m", type=float, default=0.02)
    p_mg.add_argument("--crs", type=str, default="EPSG:5186")
    p_mg.add_argument("--west", type=float, default=200_000.0)
    p_mg.add_argument("--north", type=float, default=600_000.0)

    p_e2e = sub.add_parser("e2e", help="GeoTIFF → tiles → stub SAM → mask PNG (Step 3)")
    p_e2e.add_argument("--repo-root", type=Path, default=Path("."))
    p_e2e.add_argument("--tenant-id", type=str, default="default")
    p_e2e.add_argument("--dataset-id", type=str, default="step3_e2e")
    p_e2e.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Override DATABASE_URL (default: from .env or sqlite:///./data/labeling.db)",
    )
    p_e2e.add_argument(
        "--labeling-config",
        type=str,
        default=None,
        help="Override LABELING_CONFIG_PATH (path relative to repo-root or absolute)",
    )
    p_e2e.add_argument(
        "--synthetic",
        action="store_true",
        help="Write synthetic GeoTIFF to data/source/<tenant>/raw_geotiff/<name> before tiling",
    )
    p_e2e.add_argument("--geotiff-name", type=str, default="synthetic_step3.tif", help="Filename under raw_geotiff/")
    p_e2e.add_argument(
        "--geotiff-path",
        type=Path,
        default=None,
        help="Source file when not using --synthetic (copied into raw_geotiff/)",
    )
    p_e2e.add_argument("--tile-size", type=int, default=None, help="Override active_config tiling.tile_size before dataset snapshot")
    p_e2e.add_argument("--synthetic-width", type=int, default=800)
    p_e2e.add_argument("--synthetic-height", type=int, default=600)
    p_e2e.add_argument("--pixel-size-m", type=float, default=0.02)
    p_e2e.add_argument(
        "--disk-mask",
        action="store_true",
        help="Ignore stub masks; draw occupied disk from center positive point",
    )

    return root


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "make-geotiff":
        out: Path = args.output
        write_synthetic_geotiff(
            out,
            width=args.width,
            height=args.height,
            pixel_size_m=args.pixel_size_m,
            crs=args.crs,
            west=args.west,
            north=args.north,
        )
        print(out.resolve())
        return 0
    if args.command == "e2e":
        if not args.synthetic:
            if args.geotiff_path is None:
                print("Either --synthetic or --geotiff-path is required.", file=sys.stderr)
                return 2
        return cmd_e2e(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
