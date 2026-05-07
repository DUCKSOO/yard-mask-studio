"""합성 RGB GeoTIFF 생성 — CRS·Affine 포함 (타일링·GSD 검증용).

기본은 투영 좌표계 EPSG:5186, 픽셀 크기 0.02 m (2 cm) 로
``coordinate_utils.gsd_cm_from_geotransform`` 이 약 2.0 cm/px 를 반환한다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin


def write_synthetic_geotiff(
    path: Path,
    *,
    width: int = 800,
    height: int = 600,
    pixel_size_m: float = 0.02,
    crs: str = "EPSG:5186",
    west: float = 200_000.0,
    north: float = 600_000.0,
) -> None:
    """RGB uint8 GeoTIFF 저장. north-up, 회전 없음."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_origin(west, north, pixel_size_m, pixel_size_m)

    yy, xx = np.mgrid[0:height, 0:width]
    r = ((xx * 7 + yy * 3) % 256).astype(np.uint8)
    g = ((xx * 11 + yy * 5) % 256).astype(np.uint8)
    b = ((xx * 13 + yy * 17) % 256).astype(np.uint8)
    rgb = np.stack([r, g, b], axis=0)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=3,
        dtype=rgb.dtype,
        crs=crs,
        transform=transform,
        photometric="RGB",
    ) as dst:
        dst.write(rgb)


def main() -> int:
    p = argparse.ArgumentParser(description="Write a synthetic RGB GeoTIFF for tiling / GSD tests.")
    p.add_argument("output", type=Path, help="Output path, e.g. data/source/default/raw_geotiff/synthetic.tif")
    p.add_argument("--width", type=int, default=800)
    p.add_argument("--height", type=int, default=600)
    p.add_argument("--pixel-size-m", type=float, default=0.02, help="Pixel size in meters (default 0.02 = 2 cm)")
    p.add_argument("--crs", type=str, default="EPSG:5186")
    p.add_argument("--west", type=float, default=200_000.0, help="Western edge easting (projected meters)")
    p.add_argument("--north", type=float, default=600_000.0, help="Northern edge northing (projected meters)")
    args = p.parse_args()
    write_synthetic_geotiff(
        args.output,
        width=args.width,
        height=args.height,
        pixel_size_m=args.pixel_size_m,
        crs=args.crs,
        west=args.west,
        north=args.north,
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
