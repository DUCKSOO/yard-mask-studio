import { useCallback, useEffect, useRef, useState } from "react";
import type { ToolMode } from "./ToolBar";

const LS_KEY = "yms-floating-toolbar-pos";

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

type FloatingToolBarProps = {
  tool: ToolMode;
  onToolChange: (t: ToolMode) => void;
  brushRadius: number;
  onBrushRadiusChange: (r: number) => void;
  boundsWidth: number;
  boundsHeight: number;
};

const TOOLS: { id: ToolMode; label: string; title: string }[] = [
  { id: "point", label: "점", title: "점: 좌클릭 양성 · 우클릭 음성" },
  { id: "brush", label: "브러시", title: "브러시: 좌클릭 칠하기 · 우클릭 지우개" },
];

type DragRef =
  | null
  | {
      pointerId: number;
      startX: number;
      startY: number;
      originX: number;
      originY: number;
    };

export function FloatingToolBar({
  tool,
  onToolChange,
  brushRadius,
  onBrushRadiusChange,
  boundsWidth,
  boundsHeight,
}: FloatingToolBarProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragRef>(null);
  const posRef = useRef({ x: 8, y: 48 });
  const [pos, setPos] = useState({ x: 8, y: 48 });
  const [brushPanelOpen, setBrushPanelOpen] = useState(false);
  const brushToggleRef = useRef<HTMLButtonElement>(null);
  const brushPopoverRef = useRef<HTMLDivElement>(null);

  posRef.current = pos;

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (!raw) {
        return;
      }
      const p = JSON.parse(raw) as { x?: number; y?: number };
      if (typeof p.x === "number" && typeof p.y === "number") {
        const next = { x: p.x, y: p.y };
        posRef.current = next;
        setPos(next);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!brushPanelOpen) {
      return;
    }
    const close = (e: MouseEvent) => {
      const t = e.target as Node;
      if (brushToggleRef.current?.contains(t)) {
        return;
      }
      if (brushPopoverRef.current?.contains(t)) {
        return;
      }
      setBrushPanelOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [brushPanelOpen]);

  const clampToBounds = useCallback(
    (x: number, y: number) => {
      const el = rootRef.current;
      const pw = boundsWidth;
      const ph = boundsHeight;
      if (!el || pw <= 0 || ph <= 0) {
        return { x, y };
      }
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      return {
        x: clamp(x, 0, Math.max(0, pw - w)),
        y: clamp(y, 0, Math.max(0, ph - h)),
      };
    },
    [boundsWidth, boundsHeight],
  );

  useEffect(() => {
    setPos((prev) => {
      const next = clampToBounds(prev.x, prev.y);
      posRef.current = next;
      return next;
    });
  }, [clampToBounds, boundsWidth, boundsHeight]);

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const d = dragRef.current;
      if (!d || e.pointerId !== d.pointerId) {
        return;
      }
      const nx = d.originX + (e.clientX - d.startX);
      const ny = d.originY + (e.clientY - d.startY);
      const next = clampToBounds(nx, ny);
      posRef.current = next;
      setPos(next);
    };
    const onUp = (e: PointerEvent) => {
      const d = dragRef.current;
      if (!d || e.pointerId !== d.pointerId) {
        return;
      }
      dragRef.current = null;
      try {
        localStorage.setItem(LS_KEY, JSON.stringify(posRef.current));
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [clampToBounds]);

  const onHandlePointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) {
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    const { x, y } = posRef.current;
    dragRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      originX: x,
      originY: y,
    };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const toggleBrushPanel = () => {
    setBrushPanelOpen((o) => !o);
  };

  return (
    <div
      ref={rootRef}
      className="floating-tool-bar"
      style={{ left: pos.x, top: pos.y }}
      role="toolbar"
      aria-label="라벨링 도구"
    >
      <div
        className="floating-tool-drag-handle"
        onPointerDown={onHandlePointerDown}
        title="드래그하여 위치 이동"
      >
        ⋮⋮
      </div>
      <div className="floating-tool-bar-inner">
        {TOOLS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`floating-tool-btn ${tool === t.id ? "active" : ""}`}
            title={t.title}
            aria-pressed={tool === t.id}
            onClick={() => onToolChange(t.id)}
          >
            <span className="floating-tool-btn-label">{t.label}</span>
          </button>
        ))}
        <div className="floating-brush-size-wrap">
          <button
            ref={brushToggleRef}
            type="button"
            className={`floating-tool-btn floating-brush-size-btn ${brushPanelOpen ? "active" : ""}`}
            title="브러시 크기 — 클릭하여 슬라이더"
            aria-expanded={brushPanelOpen}
            onClick={(e) => {
              e.stopPropagation();
              toggleBrushPanel();
            }}
          >
            <span className="floating-tool-btn-label">크기</span>
            <span className="floating-brush-size-value">{brushRadius}px</span>
          </button>
          {brushPanelOpen ? (
            <div ref={brushPopoverRef} className="floating-brush-popover" role="dialog" aria-label="브러시 크기">
              <label className="floating-brush-popover-label">
                반경 {brushRadius}px
                <input
                  type="range"
                  min={2}
                  max={80}
                  step={1}
                  value={brushRadius}
                  onChange={(e) => onBrushRadiusChange(Number(e.target.value))}
                />
              </label>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
