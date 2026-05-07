import { useLayoutEffect, useState } from "react";
import { Image as KonvaImage } from "react-konva";

function hexToRgba(hex: string, alpha: number): [number, number, number, number] {
  const h = hex.replace("#", "");
  const r = Number.parseInt(h.slice(0, 2), 16);
  const g = Number.parseInt(h.slice(2, 4), 16);
  const b = Number.parseInt(h.slice(4, 6), 16);
  return [r, g, b, Math.round(alpha * 255)];
}

/** 클래스 id → 반투명 오버레이 RGBA (non_occupied 는 투명) */
export function buildClassColorMap(
  definitions: { id: number; color: string }[],
): Map<number, [number, number, number, number]> {
  const m = new Map<number, [number, number, number, number]>();
  for (const d of definitions) {
    if (d.id === 0) {
      m.set(0, [0, 0, 0, 0]);
    } else {
      m.set(d.id, hexToRgba(d.color, 0.45));
    }
  }
  return m;
}

type MaskCanvasProps = {
  cells: Uint8Array;
  width: number;
  height: number;
  colorMap: Map<number, [number, number, number, number]>;
  listening: boolean;
  onPaintStart?: (x: number, y: number) => void;
  onPaintMove?: (x: number, y: number) => void;
  onPaintEnd?: () => void;
};

export function MaskCanvas(props: MaskCanvasProps) {
  const { cells, width, height, colorMap, listening, onPaintStart, onPaintMove, onPaintEnd } = props;
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null);

  useLayoutEffect(() => {
    const c = document.createElement("canvas");
    c.width = width;
    c.height = height;
    const ctx = c.getContext("2d");
    if (!ctx) {
      return;
    }
    const img = ctx.createImageData(width, height);
    const data = img.data;
    const defRgba: [number, number, number, number] = [128, 128, 128, 120];
    for (let i = 0; i < width * height; i++) {
      const id = cells[i] ?? 0;
      const rgba = colorMap.get(id) ?? defRgba;
      const o = i * 4;
      data[o] = rgba[0];
      data[o + 1] = rgba[1];
      data[o + 2] = rgba[2];
      data[o + 3] = rgba[3];
    }
    ctx.putImageData(img, 0, 0);
    setCanvas(c);
  }, [cells, width, height, colorMap]);

  if (!canvas) {
    return null;
  }

  return (
    <KonvaImage
      image={canvas}
      width={width}
      height={height}
      listening={listening}
      opacity={1}
      onMouseDown={(e) => {
        if (!listening) return;
        const pos = e.target.getRelativePointerPosition();
        if (pos) {
          onPaintStart?.(pos.x, pos.y);
        }
      }}
      onMouseMove={(e) => {
        if (!listening) return;
        if (e.evt.buttons === 0) return;
        const pos = e.target.getRelativePointerPosition();
        if (pos) {
          onPaintMove?.(pos.x, pos.y);
        }
      }}
      onMouseUp={() => {
        if (!listening) return;
        onPaintEnd?.();
      }}
      onMouseLeave={() => {
        if (!listening) return;
        onPaintEnd?.();
      }}
    />
  );
}
