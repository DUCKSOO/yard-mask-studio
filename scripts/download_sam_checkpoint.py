#!/usr/bin/env python3
"""Download Meta SAM 2.1 checkpoints and optional matching YAML configs.

Weights are distributed under Meta's SAM 2 license; see:
https://github.com/facebookresearch/sam2

Official checkpoint URLs mirror facebookresearch/sam2 ``checkpoints/download_ckpts.sh``
(base URL: https://dl.fbaipublicfiles.com/segment_anything_2/092824).

Usage (from repo root)::

    uv run python scripts/download_sam_checkpoint.py --variant hiera_large
    uv run python scripts/download_sam_checkpoint.py --variant hiera_base --with-config

Then set ``SAM_CHECKPOINT_PATH`` to the downloaded ``.pt`` file and ``SAM_MODEL_CFG`` to the
YAML name that matches your ``sam2`` install (e.g. ``sam2.1_hiera_l.yaml`` or
``sam2.1_hiera_b+.yaml`` for ``hiera_base``).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

# Same base URL as facebookresearch/sam2 checkpoints/download_ckpts.sh (SAM 2.1).
SAM21_BASE_URL = "https://dl.fbaipublicfiles.com/segment_anything_2/092824"

SAM2_CONFIG_RAW = (
    "https://raw.githubusercontent.com/facebookresearch/sam2/main/sam2/configs/sam2.1"
)

# SHA-256 of the published weights (matches Hugging Face LFS oid for the same filenames).
CHECKPOINT_SHA256: dict[str, str] = {
    "sam2.1_hiera_large.pt": (
        "2647878d5dfa5098f2f8649825738a9345572bae2d4350a2468587ece47dd318"
    ),
    "sam2.1_hiera_base_plus.pt": (
        "a2345aede8715ab1d5d31b4a509fb160c5a4af1970f199d9054ccfb746c004c5"
    ),
}

# App ``SamModelVariant`` → checkpoint file on Meta CDN + optional config filename on sam2 repo.
VARIANTS: dict[str, tuple[str, str]] = {
    "hiera_large": ("sam2.1_hiera_large.pt", "sam2.1_hiera_l.yaml"),
    "hiera_base": ("sam2.1_hiera_base_plus.pt", "sam2.1_hiera_b+.yaml"),
}


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path, *, force: bool) -> None:
    if dest.exists() and not force:
        print(f"Skip (exists): {dest}", file=sys.stderr)
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "yard-mask-studio-scripts/1.0"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            nread = 0
            with tmp.open("wb") as out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    nread += len(chunk)
                    if total:
                        pct = 100.0 * nread / total
                        print(
                            f"\r  {nread / 1e6:.1f} / {total / 1e6:.1f} MB ({pct:.0f}%)",
                            end="",
                            file=sys.stderr,
                        )
        print(file=sys.stderr)
        tmp.replace(dest)
    except BaseException:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _verify_optional(path: Path, filename: str, *, verify: bool) -> bool:
    if not verify or not path.exists():
        return True
    expected = CHECKPOINT_SHA256.get(filename)
    if not expected:
        print(
            f"Warning: no bundled SHA-256 for {filename}; skipped checksum.",
            file=sys.stderr,
        )
        return True
    actual = _sha256_file(path)
    if actual != expected:
        print(
            f"SHA-256 mismatch for {path}\n"
            f"  expected: {expected}\n"
            f"  actual:   {actual}",
            file=sys.stderr,
        )
        return False
    print(f"SHA-256 OK: {path.name}", file=sys.stderr)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download SAM 2.1 checkpoints (Meta CDN) and optional config YAML from sam2 repo.",
    )
    parser.add_argument(
        "--variant",
        choices=sorted(VARIANTS.keys()),
        default="hiera_large",
        help="Must match labeling config sam.model_variant (default: hiera_large).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("models"),
        help="Directory for the .pt file (default: ./models).",
    )
    parser.add_argument(
        "--with-config",
        action="store_true",
        help="Also download the matching sam2.1 YAML next to the checkpoint.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the target file already exists.",
    )
    parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        default=True,
        help="Verify SHA-256 when known (default: on).",
    )
    parser.add_argument(
        "--no-verify",
        dest="verify",
        action="store_false",
        help="Skip SHA-256 verification.",
    )
    args = parser.parse_args()

    ckpt_name, cfg_name = VARIANTS[args.variant]
    ckpt_url = f"{SAM21_BASE_URL}/{ckpt_name}"
    out_pt = args.output_dir / ckpt_name

    _download(ckpt_url, out_pt, force=args.force)
    if not _verify_optional(out_pt, ckpt_name, verify=args.verify):
        return 1

    if args.with_config:
        cfg_url = f"{SAM2_CONFIG_RAW}/{cfg_name}"
        out_cfg = args.output_dir / cfg_name
        _download(cfg_url, out_cfg, force=args.force)

    print(out_pt.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
