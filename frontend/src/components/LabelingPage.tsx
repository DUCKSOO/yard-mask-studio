import Konva from "konva";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Circle, Group, Layer, Rect, Stage } from "react-konva";
import {
  deleteAnnotation,
  getAnnotation,
  getTileImageUrl,
  getTileMetadata,
  getTiles,
  samPredict,
  saveAnnotation,
  type SamPrompt,
  type TileItem,
} from "../api/client";
import { GridOverlay } from "./GridOverlay";
import { buildClassColorMap, MaskCanvas } from "./MaskCanvas";
import { PromptOverlay } from "./PromptOverlay";
import { CanvasTopBar } from "./CanvasTopBar";
import { FloatingToolBar } from "./FloatingToolBar";
import { TileNavigator } from "./TileNavigator";
import { TileImageLayer, useHtmlImage } from "./TileViewer";
import { ToolBar, type ToolMode } from "./ToolBar";
import {
  applyPositiveDiskMask,
  paintBrush,
  paintBrushStroke,
  useAnnotation,
} from "../stores/annotationStore";
import { useConfig } from "../stores/configStore";
import { decodeRleVl, encodeRleVl } from "../utils/rle";
import { logger } from "../utils/logger";
import { compareTilesForNavigator, formatTileGridLabel } from "../utils/tileGrid";

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

  const [tiles, setTiles] = useState<TileItem[]>([]);
  const [tileError, setTileError] = useState<string | null>(null);
  const [selectedTileId, setSelectedTileId] = useState<string | null>(null);
  const [meta, setMeta] = useState<Record<string, unknown>>({});

  const [tool, setTool] = useState<ToolMode>("point");
  const [brushRadius, setBrushRadius] = useState(10);
  const [prompts, setPrompts] = useState<SamPrompt[]>([]);
  /** 마스크 annotation 히스토리와 동일한 커서로 프롬프트 스냅샷 유지 (Undo/Redo 동기화) */
  const PROMPTS_HISTORY_MAX = 20;
  const promptsHistoryRef = useRef<SamPrompt[][]>([[]]);
  const promptsHistoryCursor = useRef(0);
  const selectedClassId = 1; // occupied 고정
  const [samBusy, setSamBusy] = useState(false);
  /** SAM 요청 중 추가 호출 방지 (setState 비동기와의 경합 대비) */
  const samInFlight = useRef(false);
  const [samMessage, setSamMessage] = useState<string | null>(null);
  /** 켜면 점/박스 프롬프트 추가 직후 SAM 자동 실행 */
  const [autoSamRun, setAutoSamRun] = useState(true);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  /** 현재 타일에 서버 저장 어노테이션 존재 여부 — 라벨 삭제 버튼 활성화용 */
  const [hasPersistedAnnotation, setHasPersistedAnnotation] = useState(false);

  const [liveCells, setLiveCells] = useState<Uint8Array | null>(null);
  /** 브러시 모드: 포인터 주변 페인트 영역 미리보기 (이미지 좌표) */
  const [brushCursor, setBrushCursor] = useState<{ x: number; y: number; eraser: boolean } | null>(null);

  const [sidebarOpen, setSidebarOpen] = useState(true);

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 40, y: 40 });
  const panDrag = useRef<{ lastX: number; lastY: number } | null>(null);
  /** 브러시 선분 보간용 마지막 포인터 위치 (이미지 좌표, 부동소수) */
  const brushLastPos = useRef<{ x: number; y: number } | null>(null);
  /** 현재 스트로크가 지우개(우클릭 또는 지우개 도구)인지 */
  const brushStrokeEraser = useRef(false);

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

  // selectedClassId는 occupied(1) 고정; UI 선택 없음

  const displayCells = liveCells ?? ann.current;

  const tileStats = useMemo(() => {
    const total = tiles.length;
    const labeled = tiles.filter((t) => t.status === "labeled").length;
    const approved = tiles.filter((t) => t.status === "approved").length;
    return { total, labeled, approved };
  }, [tiles]);

  const selectedTileGridLabel = useMemo(() => {
    const t = tiles.find((x) => x.tile_id === selectedTileId);
    return formatTileGridLabel(t?.metadata);
  }, [tiles, selectedTileId]);

  const selectedTileIndex = useMemo(
    () => tiles.findIndex((t) => t.tile_id === selectedTileId),
    [tiles, selectedTileId],
  );

  const canPrevTile = selectedTileIndex > 0;
  const canNextTile = selectedTileIndex >= 0 && selectedTileIndex < tiles.length - 1;

  const goPrevTile = useCallback(() => {
    if (selectedTileIndex <= 0) {
      return;
    }
    const id = tiles[selectedTileIndex - 1]?.tile_id;
    if (id) {
      setSelectedTileId(id);
    }
  }, [tiles, selectedTileIndex]);

  const goNextTile = useCallback(() => {
    if (selectedTileIndex < 0 || selectedTileIndex >= tiles.length - 1) {
      return;
    }
    const id = tiles[selectedTileIndex + 1]?.tile_id;
    if (id) {
      setSelectedTileId(id);
    }
  }, [tiles, selectedTileIndex]);

  const resetPromptsHistory = useCallback(() => {
    promptsHistoryRef.current = [[]];
    promptsHistoryCursor.current = 0;
  }, []);

  const pushCellsWithSnapshot = useCallback(
    (cells: Uint8Array, currentPrompts: SamPrompt[]) => {
      let h = promptsHistoryRef.current.slice(0, promptsHistoryCursor.current + 1);
      h.push(currentPrompts.map((p) => ({ ...p })));
      if (h.length > PROMPTS_HISTORY_MAX) {
        h = h.slice(-PROMPTS_HISTORY_MAX);
      }
      promptsHistoryRef.current = h;
      promptsHistoryCursor.current = h.length - 1;
      pushCells(cells);
    },
    [pushCells],
  );

  const handleUndo = useCallback(() => {
    ann.undo();
    if (promptsHistoryCursor.current > 0) {
      promptsHistoryCursor.current -= 1;
    }
    const snap = promptsHistoryRef.current[promptsHistoryCursor.current];
    setPrompts(snap ? snap.map((p) => ({ ...p })) : []);
  }, [ann]);

  const handleRedo = useCallback(() => {
    ann.redo();
    if (promptsHistoryCursor.current < promptsHistoryRef.current.length - 1) {
      promptsHistoryCursor.current += 1;
    }
    const snap = promptsHistoryRef.current[promptsHistoryCursor.current];
    setPrompts(snap ? snap.map((p) => ({ ...p })) : []);
  }, [ann]);

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
      const sorted = [...list].sort(compareTilesForNavigator);
      setTiles(sorted);
      setSelectedTileId((prev) => prev ?? (sorted[0]?.tile_id ?? null));
      logger.info("tiles loaded", { tenantId, datasetId, count: sorted.length });
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
    brushLastPos.current = null;
    setBrushCursor(null);
  }, [selectedTileId]);

  useEffect(() => {
    if (tool !== "brush") {
      setBrushCursor(null);
    }
  }, [tool]);

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
    brushLastPos.current = null;
    setHasPersistedAnnotation(false);
    resetPromptsHistory();
    setPrompts([]);
    try {
      const m = await getTileMetadata(tenantId, datasetId, selectedTileId);
      setMeta(m);

      const url = getTileImageUrl(tenantId, datasetId, selectedTileId);
      const { w, h } = await loadImageDimensions(url);
      const tw = w;
      const th = h;

      const existing = await getAnnotation(tenantId, datasetId, selectedTileId);
      setHasPersistedAnnotation(existing !== null);
      if (existing) {
        if (existing.class_mask.width !== tw || existing.class_mask.height !== th) {
          setStatusMsg(
            `저장된 마스크 크기(${existing.class_mask.width}×${existing.class_mask.height})와 타일 이미지(${tw}×${th}) 불일치 — 빈 마스크로 시작`,
          );
          reset(tw, th);
        } else {
          const rawPrompts = existing.sam_prompts;
          const loadedPrompts: SamPrompt[] = Array.isArray(rawPrompts)
            ? (rawPrompts as SamPrompt[]).map((p) => ({ ...p }))
            : [];
          const cells = decodeRleVl(
            existing.class_mask.counts,
            existing.class_mask.height,
            existing.class_mask.width,
          );
          reset(tw, th);
          pushCellsWithSnapshot(cells, loadedPrompts);
          setPrompts(loadedPrompts);
        }
      } else {
        reset(tw, th);
      }
    } catch (e: unknown) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    }
  }, [selectedTileId, tenantId, datasetId, config, reset, pushCellsWithSnapshot, hasDataset, resetPromptsHistory]);

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
        sam_prompts: prompts.length > 0 ? prompts.map((p) => ({ ...p })) : undefined,
      });
      setStatusMsg("저장 완료");
      setHasPersistedAnnotation(true);
      logger.info("annotation saved (client)", { tenantId, datasetId, tileId: selectedTileId, w, h });
      void reloadTiles();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatusMsg(msg);
      logger.error("save failed", msg);
    }
  }, [selectedTileId, ann, annState, tenantId, datasetId, hasDataset, reloadTiles, prompts]);

  const handleDeleteLabel = useCallback(async () => {
    if (!hasDataset || !selectedTileId) {
      return;
    }
    if (
      !window.confirm(
        "이 타일의 저장된 라벨(마스크)을 삭제하고 미라벨로 되돌릴까요? 서버의 마스크 파일도 삭제됩니다.",
      )
    ) {
      return;
    }
    setStatusMsg(null);
    try {
      await deleteAnnotation(tenantId, datasetId, selectedTileId);
      setStatusMsg("라벨 삭제됨 — 타일이 미라벨로 표시됩니다.");
      logger.info("annotation deleted (client)", { tenantId, datasetId, tileId: selectedTileId });
      void reloadTiles();
      void loadTileData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatusMsg(msg);
      logger.error("delete annotation failed", msg);
    }
  }, [hasDataset, selectedTileId, tenantId, datasetId, reloadTiles, loadTileData]);

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
          handleUndo();
          return;
        }
        if (k === "y") {
          e.preventDefault();
          handleRedo();
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
        if (k === "p") {
          setTool("point");
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handleUndo, handleRedo, handleSave]);

  const { pxX, pxY } = gridPixelSize(config, meta);

  const deleteLabelTitle = useMemo(() => {
    if (!selectedTileId) {
      return "타일을 선택하세요";
    }
    if (cfgLoading) {
      return "설정 로딩 중…";
    }
    if (!hasPersistedAnnotation) {
      return "서버에 저장된 라벨이 없습니다";
    }
    return "서버에 저장된 마스크 삭제 후 미라벨로 복구";
  }, [selectedTileId, cfgLoading, hasPersistedAnnotation]);

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
    if (d) {
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
      return;
    }
    if (tool === "brush" && viewRef.current && iw > 0 && ih > 0) {
      const lp = viewRef.current.getRelativePointerPosition();
      if (!lp) {
        setBrushCursor(null);
        return;
      }
      if (lp.x < 0 || lp.x > iw || lp.y < 0 || lp.y > ih) {
        setBrushCursor(null);
        return;
      }
      const eraser = (e.evt.buttons & 2) !== 0;
      setBrushCursor({ x: lp.x, y: lp.y, eraser });
    }
  };

  const onStageMouseLeave = () => {
    panDrag.current = null;
    setBrushCursor(null);
  };

  const onStageMouseUp = () => {
    panDrag.current = null;
  };

  const handleRunSamWithPrompts = useCallback(
    async (promptList: SamPrompt[]) => {
      if (!hasDataset || !selectedTileId || !ann.current || !annState || promptList.length === 0) {
        return;
      }
      if (samInFlight.current) {
        return;
      }
      samInFlight.current = true;
      setSamBusy(true);
      setSamMessage(null);
      try {
        const res = await samPredict(
          tenantId,
          datasetId,
          selectedTileId,
          promptList,
          config?.sam.multimask_output,
        );
        const w = annState.width;
        const h = annState.height;
        let msg = `SAM 응답: 후보 ${res.candidates}개`;
        if (res.masks_rle.length > 0) {
          try {
            const binary = decodeRleVl(res.masks_rle[0], h, w);
            const base = ann.current;
            const next = new Uint8Array(base.length);
            for (let i = 0; i < base.length; i++) {
              next[i] = binary[i] === 1 ? selectedClassId : base[i]!;
            }
            pushCellsWithSnapshot(next, promptList);
            msg += " · 마스크 적용됨";
          } catch (decodeErr: unknown) {
            msg += ` · RLE 디코딩 실패: ${decodeErr instanceof Error ? decodeErr.message : String(decodeErr)}`;
          }
        } else if (res.candidates > 0 && res.mask_shape.length >= 2) {
          const lastPos = [...promptList].reverse().find((p) => p.type === "point" && p.label === "positive");
          if (lastPos && lastPos.type === "point") {
            const next = applyPositiveDiskMask(ann.current, w, h, lastPos.x, lastPos.y);
            pushCellsWithSnapshot(next, promptList);
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
        samInFlight.current = false;
        setSamBusy(false);
      }
    },
    [
      annState,
      config?.sam.multimask_output,
      datasetId,
      hasDataset,
      pushCellsWithSnapshot,
      selectedClassId,
      selectedTileId,
      tenantId,
    ],
  );

  const handleRunSam = useCallback(() => {
    void handleRunSamWithPrompts(prompts);
  }, [handleRunSamWithPrompts, prompts]);

  const hitRectMouseDown = (e: Konva.KonvaEventObject<MouseEvent>) => {
    const pos = toImageCoords(e);
    if (!pos) {
      return;
    }
    // 가운데 버튼: 어떤 도구에서든 화면 이동(히트 영역 위에서도 동작)
    if (e.evt.button === 1) {
      e.evt.preventDefault();
      const stage = e.target.getStage();
      const p = stage?.getPointerPosition();
      if (p) {
        panDrag.current = { lastX: p.x, lastY: p.y };
      }
      return;
    }
    // 우클릭: 점 모드에서 SAM 음성 프롬프트; 브러시 모드에서는 MaskCanvas가 처리
    if (e.evt.button === 2) {
      e.evt.preventDefault();
      if (tool === "point") {
        setPrompts((q) => {
          const next = [...q, { type: "point", x: pos.x, y: pos.y, label: "negative" } as const];
          if (autoSamRun) {
            queueMicrotask(() => void handleRunSamWithPrompts(next));
          }
          return next;
        });
      }
      return;
    }
    if (e.evt.button !== 0) {
      return;
    }
    if (tool === "point") {
      setPrompts((q) => {
        const next = [...q, { type: "point", x: pos.x, y: pos.y, label: "positive" } as const];
        if (autoSamRun) {
          queueMicrotask(() => void handleRunSamWithPrompts(next));
        }
        return next;
      });
    }
  };

  const onMaskPaintStart = (x: number, y: number, opts?: { eraser?: boolean }) => {
    if (tool !== "brush" || !ann.current) {
      return;
    }
    const nx = clamp(x, 0, iw - 1);
    const ny = clamp(y, 0, ih - 1);
    const isEraser = Boolean(opts?.eraser);
    brushStrokeEraser.current = isEraser;
    const classId = isEraser ? 0 : selectedClassId;
    const b = paintBrush(ann.current, iw, ih, nx, ny, brushRadius, classId);
    setLiveCells(b);
    brushLastPos.current = { x: nx, y: ny };
  };

  const onMaskPaintMove = (x: number, y: number) => {
    if (tool !== "brush" || !liveCells) {
      return;
    }
    const nx = clamp(x, 0, iw - 1);
    const ny = clamp(y, 0, ih - 1);
    const classId = brushStrokeEraser.current ? 0 : selectedClassId;
    const last = brushLastPos.current;
    if (!last) {
      brushLastPos.current = { x: nx, y: ny };
      setLiveCells((prev) => (prev ? paintBrush(prev, iw, ih, nx, ny, brushRadius, classId) : prev));
      return;
    }
    setLiveCells((prev) =>
      prev ? paintBrushStroke(prev, iw, ih, last.x, last.y, nx, ny, brushRadius, classId) : prev,
    );
    brushLastPos.current = { x: nx, y: ny };
  };

  const onMaskPaintEnd = () => {
    brushLastPos.current = null;
    brushStrokeEraser.current = false;
    if (liveCells) {
      pushCellsWithSnapshot(liveCells, prompts);
      setLiveCells(null);
    }
  };

  const showHitRect = tool !== "brush";

  return (
    <div className="app-root page-labeling-root">
      <div className="labeling-banner">
        <strong>라벨링</strong>
        <span className="muted">
          {" "}
          · 작업 데이터셋 <code>{datasetId || "—"}</code>
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

      <div className="app-body labeling-app-body">
        <aside className={`sidebar ${sidebarOpen ? "" : "sidebar--collapsed"}`}>
          {sidebarOpen ? (
            <>
              <div className="sidebar-toolbar-row">
                <button
                  type="button"
                  className="sidebar-collapse-btn"
                  onClick={() => setSidebarOpen(false)}
                  aria-label="사이드바 접기"
                  title="사이드바 접기"
                >
                  ◀
                </button>
              </div>
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
              {selectedTileId ? (
                <p className="tile-selection-hint" title={selectedTileId}>
                  선택 타일:{" "}
                  {selectedTileGridLabel ? (
                    <strong className="tile-grid-tag">{selectedTileGridLabel}</strong>
                  ) : (
                    <span className="muted">격자 정보 없음</span>
                  )}
                  <code className="tile-id-inline">{selectedTileId}</code>
                </p>
              ) : null}
              <TileNavigator
                tiles={tiles}
                selectedTileId={selectedTileId}
                onSelect={(id) => setSelectedTileId(id)}
              />
              {/* ClassPanel 숨김: 점유/비점유 이진 레이블링이므로 클래스는 occupied(1) 고정 */}
              <ToolBar tool={tool} prompts={prompts} samMessage={samMessage} />
              <div className="actions">
                <button type="button" onClick={() => void loadTileData()} disabled={!selectedTileId}>
                  다시 불러오기
                </button>
              </div>
              {cfgLoading ? <p>설정 로딩…</p> : null}
              <p className="meta-hint">
                그리드: {pxX}×{pxY}px (GSD 메타·설정 기반)
              </p>
            </>
          ) : null}
        </aside>

        {!sidebarOpen ? (
          <button
            type="button"
            className="sidebar-expand-btn"
            onClick={() => setSidebarOpen(true)}
            aria-label="사이드바 펼치기"
            title="사이드바 펼치기"
          >
            ▶
          </button>
        ) : null}

        <div className="canvas-host" ref={containerRef}>
          {hasDataset ? (
            <>
              <CanvasTopBar
                canUndo={ann.canUndo}
                canRedo={ann.canRedo}
                onUndo={handleUndo}
                onRedo={handleRedo}
                onClearPrompts={() => {
                  setPrompts([]);
                  const cur = promptsHistoryCursor.current;
                  const h = [...promptsHistoryRef.current];
                  h[cur] = [];
                  promptsHistoryRef.current = h;
                }}
                promptsEmpty={prompts.length === 0}
                onSave={() => void handleSave()}
                saveDisabled={!selectedTileId || cfgLoading}
                onDeleteLabel={() => void handleDeleteLabel()}
                deleteLabelDisabled={!selectedTileId || cfgLoading || !hasPersistedAnnotation}
                deleteLabelTitle={deleteLabelTitle}
                onRunSam={handleRunSam}
                samBusy={samBusy}
                samDisabled={prompts.length === 0}
                autoSamRun={autoSamRun}
                onAutoSamRunChange={setAutoSamRun}
                samMessage={samMessage}
                canPrevTile={canPrevTile}
                canNextTile={canNextTile}
                onPrevTile={goPrevTile}
                onNextTile={goNextTile}
                tileLabel={selectedTileGridLabel}
              />
              <FloatingToolBar
                tool={tool}
                onToolChange={setTool}
                brushRadius={brushRadius}
                onBrushRadiusChange={setBrushRadius}
                boundsWidth={stageSize.w}
                boundsHeight={stageSize.h}
              />
            </>
          ) : null}
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
              onMouseLeave={onStageMouseLeave}
              onContextMenu={(e: Konva.KonvaEventObject<MouseEvent>) => {
                e.evt.preventDefault();
              }}
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
                      listening={tool === "brush"}
                      paintEraserMode={false}
                      brushRightEraser
                      onPaintStart={onMaskPaintStart}
                      onPaintMove={onMaskPaintMove}
                      onPaintEnd={onMaskPaintEnd}
                    />
                  ) : null}
                  {tool === "brush" && brushCursor ? (
                    <Circle
                      listening={false}
                      perfectDrawEnabled={false}
                      x={brushCursor.x}
                      y={brushCursor.y}
                      radius={brushRadius}
                      stroke={brushCursor.eraser ? "#dc2626" : "#2563eb"}
                      strokeWidth={2 / Math.max(zoom, 0.05)}
                      fill={
                        brushCursor.eraser ? "rgba(220,38,38,0.14)" : "rgba(37,99,235,0.14)"
                      }
                    />
                  ) : null}
                  {showHitRect ? (
                    <Rect
                      width={iw}
                      height={ih}
                      fill="rgba(0,0,0,0)"
                      listening={!samBusy}
                      onMouseDown={hitRectMouseDown}
                    />
                  ) : null}
                  {prompts.length > 0 ? <PromptOverlay prompts={prompts} viewScale={zoom} /> : null}
                </Group>
              </Layer>
            </Stage>
          )}
        </div>
      </div>
    </div>
  );
}
