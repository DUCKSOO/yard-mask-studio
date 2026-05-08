import Konva from "konva";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Group, Layer, Rect, Stage } from "react-konva";
import {
  getAnnotation,
  getTileImageUrl,
  getTileMetadata,
  getTiles,
  samPredict,
  saveAnnotation,
  type SamPrompt,
} from "../api/client";
import { ClassPanel } from "./ClassPanel";
import { GridOverlay } from "./GridOverlay";
import { buildClassColorMap, MaskCanvas } from "./MaskCanvas";
import { TileNavigator } from "./TileNavigator";
import { TileImageLayer, useHtmlImage } from "./TileViewer";
import { ToolBar, type ToolMode } from "./ToolBar";
import {
  applyPositiveDiskMask,
  paintBrush,
  useAnnotation,
} from "../stores/annotationStore";
import { useConfig } from "../stores/configStore";
import { decodeRleVl, encodeRleVl } from "../utils/rle";
import { logger } from "../utils/logger";

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

export type LabelingPageProps = {
  tenantId: string;
  datasetId: string;
};

export function LabelingPage({ tenantId, datasetId }: LabelingPageProps) {
  const { config, loading: cfgLoading, error: cfgError } = useConfig();
  const ann = useAnnotation();
  const { reset, pushCells, state: annState } = ann;

  const [tiles, setTiles] = useState<{ tile_id: string; status: string }[]>([]);
  const [tileError, setTileError] = useState<string | null>(null);
  const [selectedTileId, setSelectedTileId] = useState<string | null>(null);
  const [meta, setMeta] = useState<Record<string, unknown>>({});

  const [tool, setTool] = useState<ToolMode>("brush");
  const [brushRadius, setBrushRadius] = useState(10);
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

  const hasDataset = Boolean(datasetId.trim());

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
      hasDataset && selectedTileId
        ? getTileImageUrl(tenantId, datasetId, selectedTileId)
        : null,
    [tenantId, datasetId, selectedTileId, hasDataset],
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

  const tileStats = useMemo(() => {
    const total = tiles.length;
    const labeled = tiles.filter((t) => t.status === "labeled").length;
    const approved = tiles.filter((t) => t.status === "approved").length;
    return { total, labeled, approved };
  }, [tiles]);

  const reloadTiles = useCallback(async () => {
    setTileError(null);
    if (!datasetId.trim()) {
      setTiles([]);
      setSelectedTileId(null);
      logger.debug("reloadTiles skipped: empty datasetId");
      return;
    }
    try {
      const list = await getTiles(tenantId, datasetId, { limit: 500 });
      setTiles(list.map((t) => ({ tile_id: t.tile_id, status: t.status })));
      setSelectedTileId((prev) => prev ?? (list[0]?.tile_id ?? null));
      logger.info("tiles loaded", { tenantId, datasetId, count: list.length });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setTileError(msg);
      logger.error("reloadTiles failed", msg);
    }
  }, [tenantId, datasetId]);

  useEffect(() => {
    setSelectedTileId(null);
  }, [tenantId, datasetId]);

  useEffect(() => {
    void reloadTiles();
  }, [reloadTiles]);

  const loadTileData = useCallback(async () => {
    if (!hasDataset || !selectedTileId || !config) {
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
          const cells = decodeRleVl(
            existing.class_mask.counts,
            existing.class_mask.height,
            existing.class_mask.width,
          );
          reset(tw, th);
          pushCells(cells);
        }
      } else {
        reset(tw, th);
      }
    } catch (e: unknown) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    }
  }, [selectedTileId, tenantId, datasetId, config, reset, pushCells, hasDataset]);

  useEffect(() => {
    void loadTileData();
  }, [loadTileData]);

  useEffect(() => {
    if (selectedTileId) {
      logger.debug("tile selected", { tenantId, datasetId, selectedTileId });
    }
  }, [selectedTileId, tenantId, datasetId]);

  const handleSave = useCallback(async () => {
    if (!hasDataset || !selectedTileId || !ann.current || !annState) {
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
      logger.info("annotation saved (client)", { tenantId, datasetId, tileId: selectedTileId, w, h });
      void reloadTiles();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatusMsg(msg);
      logger.error("save failed", msg);
    }
  }, [selectedTileId, ann, annState, tenantId, datasetId, hasDataset, reloadTiles]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName ?? "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
        return;
      }
      const k = e.key.toLowerCase();
      if (e.ctrlKey || e.metaKey) {
        if (k === "z") {
          e.preventDefault();
          ann.undo();
          return;
        }
        if (k === "y") {
          e.preventDefault();
          ann.redo();
          return;
        }
        if (k === "s") {
          e.preventDefault();
          void handleSave();
          return;
        }
      }
      if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        if (k === "b") {
          setTool("brush");
        }
        if (k === "e") {
          setTool("eraser");
        }
        if (k === "p") {
          setTool("pan");
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [ann, handleSave]);

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
    if ((tool !== "brush" && tool !== "eraser") || !ann.current) {
      return;
    }
    const nx = clamp(Math.floor(x), 0, iw - 1);
    const ny = clamp(Math.floor(y), 0, ih - 1);
    const classId = tool === "eraser" ? 0 : selectedClassId;
    const b = paintBrush(ann.current, iw, ih, nx, ny, brushRadius, classId);
    setLiveCells(b);
  };

  const onMaskPaintMove = (x: number, y: number) => {
    if ((tool !== "brush" && tool !== "eraser") || !liveCells) {
      return;
    }
    const nx = clamp(Math.floor(x), 0, iw - 1);
    const ny = clamp(Math.floor(y), 0, ih - 1);
    const classId = tool === "eraser" ? 0 : selectedClassId;
    setLiveCells((prev) =>
      prev ? paintBrush(prev, iw, ih, nx, ny, brushRadius, classId) : prev,
    );
  };

  const onMaskPaintEnd = () => {
    if (liveCells) {
      ann.pushCells(liveCells);
      setLiveCells(null);
    }
  };

  const handleRunSam = async () => {
    if (!hasDataset || !selectedTileId || !ann.current || !annState) {
      return;
    }
    setSamBusy(true);
    setSamMessage(null);
    try {
      const res = await samPredict(
        tenantId,
        datasetId,
        selectedTileId,
        prompts,
        config?.sam.multimask_output,
      );
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

  const showHitRect = tool !== "brush" && tool !== "eraser";

  return (
    <div className="app-root page-labeling-root">
      <div className="labeling-banner">
        <strong>라벨링</strong>
        <span className="muted">
          {" "}
          · 작업 대상 <code>{tenantId}</code> / <code>{datasetId || "—"}</code>
          {" · "}
          변경은 <strong>데이터셋</strong> 탭에서 하세요.
        </span>
      </div>
      {cfgError ? <p className="error labeling-inline-msg">설정 로드 실패: {cfgError}</p> : null}
      {tileError ? <p className="error labeling-inline-msg">타일 목록: {tileError}</p> : null}
      {statusMsg ? <p className="status labeling-inline-msg">{statusMsg}</p> : null}
      {!hasDataset ? (
        <p className="labeling-inline-msg muted">
          데이터셋이 선택되지 않았습니다. <strong>데이터셋</strong> 탭에서 목록을 선택하거나 생성하세요.
        </p>
      ) : null}

      <div className="app-body">
        <aside className="sidebar">
          <button type="button" onClick={() => void reloadTiles()} disabled={!hasDataset}>
            타일 목록 새로고침
          </button>
          {tileStats.total > 0 ? (
            <div className="tile-progress-bar-wrap" aria-label="진행률">
              <div
                className="tile-progress-bar tile-progress-labeled"
                style={{ width: `${(tileStats.labeled / tileStats.total) * 100}%` }}
              />
              <div
                className="tile-progress-bar tile-progress-approved"
                style={{ width: `${(tileStats.approved / tileStats.total) * 100}%` }}
              />
            </div>
          ) : null}
          <p className="tile-progress-text">
            전체 {tileStats.total} | labeled {tileStats.labeled} | approved {tileStats.approved}
          </p>
          <TileNavigator
            tiles={tiles}
            selectedTileId={selectedTileId}
            onSelect={(id) => setSelectedTileId(id)}
          />
          <ClassPanel config={config} selectedClassId={selectedClassId} onSelect={setSelectedClassId} />
          <ToolBar
            tool={tool}
            onToolChange={setTool}
            prompts={prompts}
            onClearPrompts={() => setPrompts([])}
            onRunSam={() => void handleRunSam()}
            samBusy={samBusy}
            samMessage={samMessage}
            brushRadius={brushRadius}
            onBrushRadiusChange={setBrushRadius}
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
        </aside>

        <div className="canvas-host" ref={containerRef}>
          {!hasDataset ? (
            <div className="canvas-placeholder">
              <p>데이터셋을 선택한 뒤 타일을 고르세요.</p>
            </div>
          ) : (
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
                <Group ref={viewRef} x={pan.x} y={pan.y} scaleX={zoom} scaleY={zoom}>
                  <TileImageLayer image={htmlImage} width={iw} height={ih} />
                  <GridOverlay width={iw} height={ih} gridPixelX={pxX} gridPixelY={pxY} />
                  {displayCells ? (
                    <MaskCanvas
                      cells={displayCells}
                      width={iw}
                      height={ih}
                      colorMap={colorMap}
                      listening={tool === "brush" || tool === "eraser"}
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
          )}
        </div>
      </div>
    </div>
  );
}
