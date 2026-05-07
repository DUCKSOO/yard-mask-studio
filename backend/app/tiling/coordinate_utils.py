"""GeoTransform 기반 GSD(cm/px) 및 픽셀↔미터."""

from __future__ import annotations

from typing import Any


def gsd_cm_from_geotransform(transform: Any, crs: Any | None) -> tuple[float | None, float | None, str]:
    """투영 CRS(미터)에서 pixel 크기 * 100 → cm/px. 회전이 있으면 manual 권고."""
    b = transform.b
    d = transform.d
    if abs(b) > 1e-9 or abs(d) > 1e-9:
        return None, None, "warning_needs_manual"
    px_w_m = abs(transform.a)
    px_h_m = abs(transform.e)
    if crs is None or not getattr(crs, "is_projected", False):
        return None, None, "warning_needs_manual"
    gsd_x_cm = px_w_m * 100.0
    gsd_y_cm = px_h_m * 100.0
    return gsd_x_cm, gsd_y_cm, "geotiff_transform"


def meters_per_pixel_from_gsd_cm(gsd_x_cm: float, gsd_y_cm: float) -> tuple[float, float]:
    return gsd_x_cm / 100.0, gsd_y_cm / 100.0


def pixels_for_meters(meters: float, gsd_cm: float) -> int:
    return int(meters * 100.0 / gsd_cm)
