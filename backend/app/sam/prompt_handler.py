"""SAM 프롬프트 파싱 및 좌표 클램프."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PointPrompt:
    x: int
    y: int
    label: str  # positive | negative


@dataclass
class BoxPrompt:
    x1: int
    y1: int
    x2: int
    y2: int


def clamp_point(x: int, y: int, width: int, height: int) -> tuple[int, int]:
    return max(0, min(width - 1, x)), max(0, min(height - 1, y))


def clamp_box(x1: int, y1: int, x2: int, y2: int, width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1 = clamp_point(x1, y1, width, height)
    x2, y2 = clamp_point(x2, y2, width, height)
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return x1, y1, x2, y2


def parse_prompts(raw: list[dict], width: int, height: int) -> list[PointPrompt | BoxPrompt]:
    out: list[PointPrompt | BoxPrompt] = []
    for p in raw:
        t = p.get("type")
        if t == "point":
            x, y = clamp_point(int(p["x"]), int(p["y"]), width, height)
            lab = str(p.get("label", "positive"))
            if lab not in ("positive", "negative"):
                raise ValueError("point label must be positive or negative")
            out.append(PointPrompt(x=x, y=y, label=lab))
        elif t == "box":
            x1, y1, x2, y2 = clamp_box(
                int(p["x1"]), int(p["y1"]), int(p["x2"]), int(p["y2"]), width, height
            )
            out.append(BoxPrompt(x1=x1, y1=y1, x2=x2, y2=y2))
        else:
            raise ValueError(f"unknown prompt type {t}")
    return out
