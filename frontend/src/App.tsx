import Konva from "konva";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Group, Layer, Rect, Stage } from "react-konva";
import {
  getAnnotation,
  getTileMetadata,
  getTileImageUrl,
  getTiles,
  samPredict,
  saveAnnotation,
  type SamPrompt,
} from "./api/client";
import { ClassPanel } from "./components/ClassPanel";
import { GridOverlay } from "./components/GridOverlay";
import { buildClassColorMap, MaskCanvas } from "./components/MaskCanvas";
import { ReviewPanel } from "./components/ReviewPanel";
import { TileImageLayer, useHtmlImage } from "./components/TileViewer";
import { ToolBar, type ToolMode } from "./components/ToolBar";
import {
  AnnotationProvider,
  applyPositiveDiskMask,
  paintBrush,
  useAnnotation,
} from "./stores/annotationStore";
import { ConfigProvider, useConfig } from "./stores/configStore";
import { decodeRleVl, encodeRleVl } from "./utils/rle";

const DEFAULT_TENANT = import.meta.env.VITE_TENANT_ID ?? "default";
const DEFAULT_DATASET = import.meta.env.VITE_DATASET_ID ?? "step3_e2e";

const BRUSH_RADIUS = 10;

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function loadImageDimensions(src: string): Promise<{ w: number; h: number }> {
  return new Promise((resolve, reject) => {
    const i = new window.Image();
    i.crossOrigin = "anonymous";
    i.onload = () => resolve({ w: i.naturalWidth, h: i.naturalHeight });
    i.onerror = () => reject(new Error(`이미지 로드 실패: ${src}`));
    i.src = src;
  });
}

function gridPixelSize(
  cfg: ReturnType<typeof useConfig>["config"],
  meta: Record<string, unknown>,
): { pxX: number; pxY: number } {
  if (!cfg) {
    return { pxX: 64, pxY: 64 };
  }
  const mx = Number(meta.measured_gsd_x_cm);
  const gx = Number.isFinite(mx) && mx > 0 ? mx : cfg.geo.expected_gsd_cm;
  const my = Number(meta.measured_gsd_y_cm);
  const gy = Number.isFinite(my) && my > 0 ? my : cfg.geo.expected_gsd_cm;
  const pxX = Math.max(1, Math.floor((cfg.grid.size_meters * 100) / gx));
  const pxY = Math.max(1, Math.floor((cfg.grid.size_meters * 100) / gy));
  return { pxX, pxY };
}

function InnerApp() {
  const { config, loading: cfgLoading, error: cfgError } = useConfig();
  const ann = useAnnotation();
  const { reset, pushCells, state: annState } = ann;

  const [tenantId, setTenantId] = useState(DEFAULT_TENANT);
  const [datasetId, setDatasetId] = useState(DEFAULT_DATASET);
  const [tiles, setTiles] = useState<{ tile_id: string; status: string }[]>([]);
  const [tileError, setTileError] = useState<string | null>(null);
  const [selectedTileId, setSelectedTileId] = useState<string | null>(null);
  const [meta, setMeta] = useState<Record<string, unknown>>({});

  const [tool, setTool] = useState<ToolMode>("brush");
  const [prompts, setPrompts] = useState<SamPrompt[]>([]);
  const [selectedClassId, setSelectedClassId] = useState(1);
  const [samBusy, setSamBusy] = useState(false);
  const [samMessage, setSamMessage] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const [liveCells, setLiveCells] = useState<Uint8Array | null>(null);

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 40, y: 40 });
  const panDrag = useRef<{ lastX: number; lastY: number } | null>(null);
  const boxStart = useRef<{ x: number; y: number } | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const [stageSize, setStageSize] = useState({ w: 800, h: 560 });
  const viewRef = useRef<Konva.Group>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setStageSize({ w: Math.floor(r.width), h: Math.floor(r.height) });
    });
    ro.observe(el);
    const r = el.getBoundingClientRect();
    setStageSize({ w: Math.floor(r.width), h: Math.floor(r.height) });
    return () => ro.disconnect();
  }, []);

  const imageUrl = useMemo(
    () =>
      selectedTileId ? getTileImageUrl(tenantId, datasetId, selectedTileId) : null,
    [tenantId, datasetId, selectedTileId],
  );
  const htmlImage = useHtmlImage(imageUrl);

  const iw = htmlImage ? htmlImage.naturalWidth : Number(meta.tile_size) || 512;
  const ih = htmlImage ? htmlImage.naturalHeight : Number(meta.tile_size) || 512;

  const colorMap = useMemo(() => {
    if (!config) {
      return new Map<number, [number, number, number, number]>([
        [0, [0, 0, 0, 0]],
        [1, [255, 0, 0, 115]],
        [255, [128, 128, 128, 115]],
      ]);
    }
    return buildClassColorMap(config.classes.definitions);
  }, [config]);

  const displayCells = liveCells ?? ann.current;

  const reloadTiles = useCallback(async () => {
    setTileError(null);
    try {
      const list = await getTiles(tenantId, datasetId, { limit: 500 });
      setTiles(list.map((t) => ({ tile_id: t.tile_id, status: t.status })));
      setSelectedTileId((prev) => prev ?? (list[0]?.tile_id ?? null));
    } catch (e: unknown) {
      setTileError(e instanceof Error ? e.message : String(e));
    }
  }, [tenantId, datasetId]);

  useEffect(() => {
    setSelectedTileId(null);
  }, [tenantId, datasetId]);

  useEffect(() => {
    void reloadTiles();
  }, [reloadTiles]);

  const loadTileData = useCallback(async () => {
    if (!selectedTileId || !config) {
      return;
    }
    setSamMessage(null);
    setStatusMsg(null);
    setLiveCells(null);
    setPrompts([]);
    try {
      const m = await getTileMetadata(tenantId, datasetId, selectedTileId);
      setMeta(m);

      const url = getTileImageUrl(tenantId, datasetId, selectedTileId);
      const { w, h } = await loadImageDimensions(url);
      const tw = w;
      const th = h;

      const existing = await getAnnotation(tenantId, datasetId, selectedTileId);
      if (existing) {
        if (existing.class_mask.width !== tw || existing.class_mask.height !== th) {
          setStatusMsg(
            `저장된 마스크 크기(${existing.class_mask.width}×${existing.class_mask.height})와 타일 이미지(${tw}×${th}) 불일치 — 빈 마스크로 시작`,
          );
          reset(tw, th);
        } else {
          const cells = decodeRleVl(existing.class_mask.counts, existing.class_mask.height, existing.class_mask.width);
          reset(tw, th);
          pushCells(cells);
        }
      } else {
        reset(tw, th);
      }
    } catch (e: unknown) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    }
  }, [selectedTileId, tenantId, datasetId, config, reset, pushCells]);

  useEffect(() => {
    void loadTileData();
  }, [loadTileData]);

  /** PNG 실제 크기는 타일 메타/저장 annotation 과 일치한다고 가정 (불일치 시 다시 불러오기 사용). */

  const { pxX, pxY } = gridPixelSize(config, meta);

  const toImageCoords = useCallback(
    (_evt: Konva.KonvaEventObject<MouseEvent>): { x: number; y: number } | null => {
      const g = viewRef.current;
      if (!g) {
        return null;
      }
      const p = g.getRelativePointerPosition();
      if (!p) {
        return null;
      }
      return {
        x: clamp(Math.floor(p.x), 0, iw - 1),
        y: clamp(Math.floor(p.y), 0, ih - 1),
      };
    },
    [iw, ih],
  );

  const handleWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault();
    const stage = e.target.getStage();
    if (!stage) {
      return;
    }
    const pointer = stage.getPointerPosition();
    if (!pointer) {
      return;
    }
    const oldScale = zoom;
    const direction = e.evt.deltaY > 0 ? -1 : 1;
    const next = direction > 0 ? oldScale * 1.08 : oldScale / 1.08;
    const newScale = clamp(next, 0.15, 10);
    const mousePointTo = {
      x: (pointer.x - pan.x) / oldScale,
      y: (pointer.y - pan.y) / oldScale,
    };
    setPan({
      x: pointer.x - mousePointTo.x * newScale,
      y: pointer.y - mousePointTo.y * newScale,
    });
    setZoom(newScale);
  };

  const onStageMouseDown = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (e.evt.button === 1) {
      const stage = e.target.getStage();
      const p = stage?.getPointerPosition();
      if (p) {
        panDrag.current = { lastX: p.x, lastY: p.y };
      }
    }
  };

  const onStageMouseMove = (e: Konva.KonvaEventObject<MouseEvent>) => {
    const d = panDrag.current;
    if (!d) {
      return;
    }
    const stage = e.target.getStage();
    const p = stage?.getPointerPosition();
    if (!p) {
      return;
    }
    setPan((prev) => ({
      x: prev.x + (p.x - d.lastX),
      y: prev.y + (p.y - d.lastY),
    }));
    panDrag.current = { lastX: p.x, lastY: p.y };
  };

  const onStageMouseUp = () => {
    panDrag.current = null;
  };

  const hitRectMouseDown = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (e.evt.button !== 0) {
      return;
    }
    const pos = toImageCoords(e);
    if (!pos) {
      return;
    }
    if (tool === "pan") {
      const stage = e.target.getStage();
      const p = stage?.getPointerPosition();
      if (p) {
        panDrag.current = { lastX: p.x, lastY: p.y };
      }
      return;
    }
    if (tool === "point_pos") {
      setPrompts((q) => [...q, { type: "point", x: pos.x, y: pos.y, label: "positive" }]);
      return;
    }
    if (tool === "point_neg") {
      setPrompts((q) => [...q, { type: "point", x: pos.x, y: pos.y, label: "negative" }]);
      return;
    }
    if (tool === "box") {
      boxStart.current = { x: pos.x, y: pos.y };
    }
  };

  const hitRectMouseUp = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (tool !== "box" || !boxStart.current) {
      return;
    }
    const pos = toImageCoords(e);
    if (!pos) {
      boxStart.current = null;
      return;
    }
    const x1 = Math.min(boxStart.current.x, pos.x);
    const x2 = Math.max(boxStart.current.x, pos.x);
    const y1 = Math.min(boxStart.current.y, pos.y);
    const y2 = Math.max(boxStart.current.y, pos.y);
    boxStart.current = null;
    if (x2 - x1 < 2 || y2 - y1 < 2) {
      return;
    }
    setPrompts((q) => [...q, { type: "box", x1, y1, x2, y2 }]);
  };

  const onMaskPaintStart = (x: number, y: number) => {
    if (tool !== "brush" || !ann.current) {
      return;
    }
    const nx = clamp(Math.floor(x), 0, iw - 1);
    const ny = clamp(Math.floor(y), 0, ih - 1);
    const b = paintBrush(ann.current, iw, ih, nx, ny, BRUSH_RADIUS, selectedClassId);
    setLiveCells(b);
  };

  const onMaskPaintMove = (x: number, y: number) => {
    if (tool !== "brush" || !liveCells) {
      return;
    }
    const nx = clamp(Math.floor(x), 0, iw - 1);
    const ny = clamp(Math.floor(y), 0, ih - 1);
    setLiveCells((prev) =>
      prev ? paintBrush(prev, iw, ih, nx, ny, BRUSH_RADIUS, selectedClassId) : prev,
    );
  };

  const onMaskPaintEnd = () => {
    if (liveCells) {
      ann.pushCells(liveCells);
      setLiveCells(null);
    }
  };

  const handleSave = async () => {
    if (!selectedTileId || !ann.current || !annState) {
      return;
    }
    setStatusMsg(null);
    try {
      const w = annState.width;
      const h = annState.height;
      const counts = encodeRleVl(ann.current, w, h);
      await saveAnnotation(tenantId, datasetId, selectedTileId, {
        status: "labeled",
        mask_encoding: "rle",
        class_mask: { height: h, width: w, counts },
      });
      setStatusMsg("저장 완료");
    } catch (e: unknown) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const handleRunSam = async () => {
    if (!selectedTileId || !ann.current || !annState) {
      return;
    }
    setSamBusy(true);
    setSamMessage(null);
    try {
      const res = await samPredict(tenantId, datasetId, selectedTileId, prompts, config?.sam.multimask_output);
      const w = annState.width;
      const h = annState.height;
      let msg = `SAM 응답: 후보 ${res.candidates}개`;
      if (res.candidates > 0 && res.mask_shape.length >= 2) {
        const lastPos = [...prompts].reverse().find((p) => p.type === "point" && p.label === "positive");
        if (lastPos && lastPos.type === "point") {
          const next = applyPositiveDiskMask(ann.current, w, h, lastPos.x, lastPos.y);
          pushCells(next);
          msg += " · 스텁 영역 병합(API가 픽셀 미반환 시)";
        } else {
          msg += " · 양성 점 없음 — 브러시로 편집";
        }
      } else {
        msg += " · 후보 없음 — 브러시로 편집";
      }
      setSamMessage(msg);
    } catch (e: unknown) {
      setSamMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setSamBusy(false);
    }
  };

  const showHitRect = tool !== "brush";

  return (
    <div className="app-root">
      <header className="app-header">
        <h1>yard-mask-studio</h1>
        {cfgError ? <p className="error">설정 로드 실패: {cfgError}</p> : null}
        {tileError ? <p className="error">타일 목록: {tileError}</p> : null}
        {statusMsg ? <p className="status">{statusMsg}</p> : null}
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <label>
            tenant
            <input value={tenantId} onChange={(e) => setTenantId(e.target.value)} />
          </label>
          <label>
            dataset
            <input value={datasetId} onChange={(e) => setDatasetId(e.target.value)} />
          </label>
          <button type="button" onClick={() => void reloadTiles()}>
            타일 목록 새로고침
          </button>
          <label>
            타일
            <select
              value={selectedTileId ?? ""}
              onChange={(e) => setSelectedTileId(e.target.value || null)}
            >
              <option value="">— 선택 —</option>
              {tiles.map((t) => (
                <option key={t.tile_id} value={t.tile_id}>
                  {t.tile_id} ({t.status})
                </option>
              ))}
            </select>
          </label>
          <ClassPanel config={config} selectedClassId={selectedClassId} onSelect={setSelectedClassId} />
          <ToolBar
            tool={tool}
            onToolChange={setTool}
            prompts={prompts}
            onClearPrompts={() => setPrompts([])}
            onRunSam={() => void handleRunSam()}
            samBusy={samBusy}
            samMessage={samMessage}
          />
          <div className="actions">
            <button type="button" onClick={() => ann.undo()} disabled={!ann.canUndo}>
              Undo
            </button>
            <button type="button" onClick={() => ann.redo()} disabled={!ann.canRedo}>
              Redo
            </button>
            <button type="button" onClick={() => void handleSave()} disabled={!selectedTileId || cfgLoading}>
              저장
            </button>
            <button type="button" onClick={() => void loadTileData()} disabled={!selectedTileId}>
              다시 불러오기
            </button>
          </div>
          {cfgLoading ? <p>설정 로딩…</p> : null}
          <p className="meta-hint">
            그리드: {pxX}×{pxY}px (GSD 메타·설정 기반)
          </p>
          <ReviewPanel tenantId={tenantId} />
        </aside>

        <div className="canvas-host" ref={containerRef}>
          <Stage
            width={stageSize.w}
            height={stageSize.h}
            onWheel={handleWheel}
            onMouseDown={onStageMouseDown}
            onMouseMove={onStageMouseMove}
            onMouseUp={onStageMouseUp}
            onMouseLeave={onStageMouseUp}
          >
            <Layer>
              <Group
                ref={viewRef}
                x={pan.x}
                y={pan.y}
                scaleX={zoom}
                scaleY={zoom}
              >
                <TileImageLayer image={htmlImage} width={iw} height={ih} />
                <GridOverlay width={iw} height={ih} gridPixelX={pxX} gridPixelY={pxY} />
                {displayCells ? (
                  <MaskCanvas
                    cells={displayCells}
                    width={iw}
                    height={ih}
                    colorMap={colorMap}
                    listening={tool === "brush"}
                    onPaintStart={onMaskPaintStart}
                    onPaintMove={onMaskPaintMove}
                    onPaintEnd={onMaskPaintEnd}
                  />
                ) : null}
                {showHitRect ? (
                  <Rect
                    width={iw}
                    height={ih}
                    fill="rgba(0,0,0,0)"
                    listening
                    onMouseDown={hitRectMouseDown}
                    onMouseUp={hitRectMouseUp}
                    onMouseMove={(e: Konva.KonvaEventObject<MouseEvent>) => {
                      if (tool === "pan" && panDrag.current && e.evt.buttons === 1) {
                        onStageMouseMove(e);
                      }
                    }}
                  />
                ) : null}
              </Group>
            </Layer>
          </Stage>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ConfigProvider>
      <AnnotationProvider>
        <InnerApp />
      </AnnotationProvider>
    </ConfigProvider>
  );
}
