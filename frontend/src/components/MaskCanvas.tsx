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

export type PaintStrokeOptions = {
  /** 브러시 도구일 때 우클릭으로 시작한 지우개 스트로크 */
  eraser?: boolean;
};

type MaskCanvasProps = {
  cells: Uint8Array;
  width: number;
  height: number;
  colorMap: Map<number, [number, number, number, number]>;
  listening: boolean;
  /** tool === eraser 일 때 true — 좌클릭만 지우개 */
  paintEraserMode?: boolean;
  /** tool === brush 일 때 true — 우클릭 드래그를 지우개로 처리 */
  brushRightEraser?: boolean;
  onPaintStart?: (x: number, y: number, opts?: PaintStrokeOptions) => void;
  onPaintMove?: (x: number, y: number) => void;
  onPaintEnd?: () => void;
};

export function MaskCanvas(props: MaskCanvasProps) {
  const {
    cells,
    width,
    height,
    colorMap,
    listening,
    paintEraserMode = false,
    brushRightEraser = false,
    onPaintStart,
    onPaintMove,
    onPaintEnd,
  } = props;
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
        const btn = e.evt.button;
        if (btn === 2 && brushRightEraser) {
          e.evt.preventDefault();
        }
        if (btn !== 0 && !(btn === 2 && brushRightEraser)) return;
        const pos = e.target.getRelativePointerPosition();
        if (pos) {
          const eraser = paintEraserMode || (btn === 2 && brushRightEraser);
          onPaintStart?.(pos.x, pos.y, eraser ? { eraser: true } : undefined);
        }
      }}
      onMouseMove={(e) => {
        if (!listening) return;
        const left = (e.evt.buttons & 1) !== 0;
        const right = (e.evt.buttons & 2) !== 0;
        if (!left && !(brushRightEraser && right)) return;
        const pos = e.target.getRelativePointerPosition();
        if (pos) {
          onPaintMove?.(pos.x, pos.y);
        }
      }}
      onMouseUp={(e) => {
        if (!listening) return;
        const btn = e.evt.button;
        if (btn !== 0 && !(btn === 2 && brushRightEraser)) return;
        onPaintEnd?.();
      }}
      onMouseLeave={() => {
        if (!listening) return;
        onPaintEnd?.();
      }}
    />
  );
}
