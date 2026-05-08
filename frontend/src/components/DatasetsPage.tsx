import { isAxiosError } from "axios";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  createDataset,
  deleteDataset,
  deleteGeotiff,
  generateTiles,
  getExportDownloadUrl,
  getExportStatus,
  listDatasets,
  listGeotiffs,
  triggerExport,
  uploadGeotiff,
  type DatasetListItem,
  type GeotiffListItem,
} from "../api/client";
import { ConfigImpactWidget } from "./ConfigImpactWidget";
import { logger } from "../utils/logger";

type ExportRowState = {
  phase: "exporting" | "done" | "error";
  exportId: string | null;
  sampleCount: number;
  errMsg: string | null;
};

function formatBytes(n: number): string {
  if (n < 1024) {
    return `${n} B`;
  }
  if (n < 1024 * 1024) {
    return `${(n / 1024).toFixed(1)} KB`;
  }
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatApiError(e: unknown): string {
  if (isAxiosError(e)) {
    const d = e.response?.data as { detail?: unknown } | undefined;
    const detail = d?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item: unknown) =>
          typeof item === "object" && item !== null && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : JSON.stringify(item),
        )
        .join("; ");
    }
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

type DatasetsPageProps = {
  tenantId: string;
  selectedDatasetId: string;
  onSelectDataset: (id: string) => void;
  onGoToLabeling: (datasetId: string) => void;
};

type PendingExportKind = { kind: "single"; datasetId: string } | { kind: "bulk" };

type TileGenJob = {
  datasetId: string;
  sourceGeotiff: string;
  settle?: {
    resolve: (payload?: { tilesCreated: number }) => void;
    reject: (e: unknown) => void;
  };
};

export function DatasetsPage({
  tenantId,
  selectedDatasetId,
  onSelectDataset,
  onGoToLabeling,
}: DatasetsPageProps) {
  const [setupModalOpen, setSetupModalOpen] = useState(false);

  const [rows, setRows] = useState<DatasetListItem[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listMsg, setListMsg] = useState<string | null>(null);
  const [listErr, setListErr] = useState<string | null>(null);
  const tileGenQueueRef = useRef<TileGenJob[]>([]);
  const tileGenDrainingRef = useRef(false);
  const tileGenRunningRef = useRef<string | null>(null);
  const [tileGenRunningId, setTileGenRunningId] = useState<string | null>(null);
  const [tileGenQueuedIds, setTileGenQueuedIds] = useState<string[]>([]);
  const [rowDeleteBusy, setRowDeleteBusy] = useState<string | null>(null);

  const [newDatasetId, setNewDatasetId] = useState("");
  const [geotiffFiles, setGeotiffFiles] = useState<GeotiffListItem[]>([]);
  const [selectedGeotiff, setSelectedGeotiff] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [uploadTotal, setUploadTotal] = useState(0);
  /** 타일 생성 API 진행 중 — 하단 토스트용 (퍼센트 없음) */
  const [tileGenToast, setTileGenToast] = useState<null | { datasetId: string; queueBehind: number }>(null);
  const [geotiffDeleteBusy, setGeotiffDeleteBusy] = useState<string | null>(null);
  const [createBusy, setCreateBusy] = useState(false);
  const [createMsg, setCreateMsg] = useState<string | null>(null);
  const [createErr, setCreateErr] = useState<string | null>(null);

  const [exportMap, setExportMap] = useState<Record<string, ExportRowState>>({});
  const [bulkExportBusy, setBulkExportBusy] = useState(false);
  const [impactModalOpen, setImpactModalOpen] = useState(false);
  const [pendingExport, setPendingExport] = useState<PendingExportKind | null>(null);

  const refreshList = useCallback(async () => {
    setListError(null);
    setListLoading(true);
    try {
      const list = await listDatasets(tenantId);
      setRows(list);
      logger.info("datasets list loaded", { tenantId, count: list.length });
    } catch (e: unknown) {
      setListError(e instanceof Error ? e.message : String(e));
      logger.error("datasets list failed", e);
    } finally {
      setListLoading(false);
    }
  }, [tenantId]);

  const syncTileGenQueueUi = useCallback(() => {
    setTileGenQueuedIds(tileGenQueueRef.current.map((j) => j.datasetId));
  }, []);

  const runTileGenWorker = useCallback(async () => {
    if (tileGenDrainingRef.current) {
      return;
    }
    tileGenDrainingRef.current = true;
    try {
      while (tileGenQueueRef.current.length > 0) {
        const job = tileGenQueueRef.current.shift()!;
        syncTileGenQueueUi();
        tileGenRunningRef.current = job.datasetId;
        setTileGenRunningId(job.datasetId);
        setTileGenToast({
          datasetId: job.datasetId,
          queueBehind: tileGenQueueRef.current.length,
        });
        try {
          const { tiles_created } = await generateTiles(tenantId, job.datasetId, job.sourceGeotiff);
          setListMsg(`"${job.datasetId}" 타일 ${tiles_created}개 생성됨.`);
          await refreshList();
          logger.info("tiles generated (queue)", { tenantId, datasetId: job.datasetId, tiles_created });
          job.settle?.resolve({ tilesCreated: tiles_created });
        } catch (e: unknown) {
          setListErr(formatApiError(e));
          job.settle?.reject(e);
        } finally {
          tileGenRunningRef.current = null;
        }
      }
    } finally {
      setTileGenRunningId(null);
      setTileGenToast(null);
      syncTileGenQueueUi();
      tileGenDrainingRef.current = false;
    }
  }, [tenantId, refreshList, syncTileGenQueueUi]);

  const enqueueTileGeneration = useCallback(
    (
      datasetId: string,
      sourceGeotiff: string,
      settle?: TileGenJob["settle"],
    ): boolean => {
      if (tileGenRunningRef.current === datasetId) {
        settle?.reject(new Error("이미 해당 데이터셋의 타일을 생성 중입니다."));
        return false;
      }
      if (tileGenQueueRef.current.some((j) => j.datasetId === datasetId)) {
        settle?.reject(new Error("이미 대기열에 있습니다."));
        return false;
      }
      tileGenQueueRef.current.push({ datasetId, sourceGeotiff, settle });
      syncTileGenQueueUi();
      void runTileGenWorker();
      return true;
    },
    [runTileGenWorker, syncTileGenQueueUi],
  );

  const refreshGeotiffs = useCallback(async () => {
    try {
      const list = await listGeotiffs(tenantId);
      setGeotiffFiles(list);
      logger.info("geotiff list loaded", { tenantId, count: list.length });
    } catch (e: unknown) {
      logger.error("geotiff list failed", e);
      setGeotiffFiles([]);
    }
  }, [tenantId]);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  useEffect(() => {
    void refreshGeotiffs();
  }, [refreshGeotiffs]);

  useEffect(() => {
    setSelectedGeotiff("");
  }, [tenantId]);

  useEffect(() => {
    if (!setupModalOpen) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSetupModalOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setupModalOpen]);

  useEffect(() => {
    if (!setupModalOpen && !impactModalOpen) {
      return;
    }
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [setupModalOpen, impactModalOpen]);

  useEffect(() => {
    if (!impactModalOpen) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setImpactModalOpen(false);
        setPendingExport(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [impactModalOpen]);

  const openSetupModal = () => {
    setSetupModalOpen(true);
    void refreshGeotiffs();
  };

  const handleGeotiffUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.target;
    const rawList = input.files;
    if (!rawList?.length) {
      return;
    }
    /** 먼저 File 배열로 복사한 뒤 input을 비웁니다. 비우면 FileList가 비어 업로드가 실패합니다. */
    const files = Array.from(rawList);
    input.value = "";

    setCreateErr(null);
    setCreateMsg(null);
    setUploadBusy(true);
    setUploadTotal(files.length);
    const progresses = files.map(() => 0);
    const updateOverallPct = () => {
      const sum = progresses.reduce((a, b) => a + b, 0);
      setUploadPct(Math.round(sum / files.length));
    };
    setUploadPct(0);
    try {
      const results = await Promise.allSettled(
        files.map((file, i) =>
          uploadGeotiff(tenantId, file, (p) => {
            progresses[i] = p;
            updateOverallPct();
          }),
        ),
      );
      await refreshGeotiffs();
      const ok: string[] = [];
      const failNames: string[] = [];
      const failReasons: string[] = [];
      results.forEach((r, i) => {
        if (r.status === "fulfilled") {
          ok.push(r.value.filename);
        } else {
          failNames.push(files[i].name);
          failReasons.push(formatApiError(r.reason));
        }
      });
      if (ok.length > 0) {
        setSelectedGeotiff(ok[ok.length - 1]!);
      }
      if (failNames.length === 0) {
        setCreateMsg(
          ok.length > 1 ? `업로드 완료: ${ok.length}개` : `업로드 완료: ${ok[0] ?? ""}`,
        );
      } else if (ok.length > 0) {
        setCreateMsg(`${ok.length}개 업로드됨.`);
        setCreateErr(
          `${failNames.length}개 실패: ${failNames.slice(0, 5).join(", ")}${failNames.length > 5 ? " …" : ""}` +
            (failReasons[0] ? ` (${failReasons[0]})` : ""),
        );
      } else {
        const detail = failReasons[0] ?? "";
        setCreateErr(
          detail
            ? `업로드 실패: ${detail}`
            : `업로드 실패 (${failNames.length}개): ${failNames.slice(0, 5).join(", ")}${failNames.length > 5 ? " …" : ""}`,
        );
      }
    } catch (err: unknown) {
      setCreateErr(formatApiError(err));
    } finally {
      setUploadBusy(false);
      setUploadPct(null);
      setUploadTotal(0);
    }
  };

  const handleDeleteGeotiffFile = async (filename: string) => {
    if (
      !window.confirm(
        `서버에서 이 GeoTIFF 파일을 삭제할까요?\n${filename}\n(데이터셋에 연결된 이름은 그대로일 수 있습니다.)`,
      )
    ) {
      return;
    }
    setGeotiffDeleteBusy(filename);
    setCreateErr(null);
    try {
      await deleteGeotiff(tenantId, filename);
      if (selectedGeotiff === filename) {
        setSelectedGeotiff("");
      }
      await refreshGeotiffs();
      setCreateMsg(`삭제됨: ${filename}`);
    } catch (err: unknown) {
      setCreateErr(formatApiError(err));
    } finally {
      setGeotiffDeleteBusy(null);
    }
  };

  const handleCreateOnly = async () => {
    const id = newDatasetId.trim();
    if (!id) {
      setCreateErr("dataset ID를 입력하세요.");
      return;
    }
    setCreateErr(null);
    setCreateMsg(null);
    setCreateBusy(true);
    try {
      const geo = selectedGeotiff.trim();
      const { dataset_id } = await createDataset(tenantId, id, geo === "" ? null : geo);
      setCreateMsg(`데이터셋 "${dataset_id}" 생성됨.`);
      onSelectDataset(dataset_id);
      await refreshList();
      logger.info("dataset created", { tenantId, dataset_id });
    } catch (e: unknown) {
      setCreateErr(formatApiError(e));
    } finally {
      setCreateBusy(false);
    }
  };

  const handleCreateAndTiles = async () => {
    const id = newDatasetId.trim();
    if (!id) {
      setCreateErr("dataset ID를 입력하세요.");
      return;
    }
    const geo = selectedGeotiff.trim();
    if (!geo) {
      setCreateErr("아래 원본 표에서 GeoTIFF를 선택하거나 먼저 업로드하세요.");
      return;
    }
    setCreateErr(null);
    setCreateMsg(null);
    setCreateBusy(true);
    try {
      const { dataset_id } = await createDataset(tenantId, id, geo);
      const tileResult = await new Promise<{ tilesCreated: number }>((resolve, reject) => {
        const ok = enqueueTileGeneration(dataset_id, geo, {
          resolve: (p) => resolve(p ?? { tilesCreated: 0 }),
          reject,
        });
        if (!ok) {
          reject(new Error("타일 생성 대기열에 추가하지 못했습니다."));
        }
      });
      setCreateMsg(`데이터셋 "${dataset_id}" 생성 · 타일 ${tileResult.tilesCreated}개 생성됨.`);
      onSelectDataset(dataset_id);
      logger.info("dataset created with tiles", { tenantId, dataset_id, tiles_created: tileResult.tilesCreated });
    } catch (e: unknown) {
      setCreateErr(formatApiError(e));
    } finally {
      setCreateBusy(false);
    }
  };

  const handleRowGenerateTiles = (datasetId: string, sourceGeotiff: string) => {
    setListErr(null);
    setListMsg(null);
    enqueueTileGeneration(datasetId, sourceGeotiff);
  };

  const resetExportRow = useCallback((datasetId: string) => {
    setExportMap((prev) => {
      const next = { ...prev };
      delete next[datasetId];
      return next;
    });
  }, []);

  const runExportForDataset = useCallback(
    async (datasetId: string): Promise<boolean> => {
      setExportMap((prev) => ({
        ...prev,
        [datasetId]: {
          phase: "exporting",
          exportId: null,
          sampleCount: 0,
          errMsg: null,
        },
      }));
      try {
        const { export_id } = await triggerExport(tenantId, datasetId);
        setExportMap((prev) => ({
          ...prev,
          [datasetId]: {
            ...prev[datasetId]!,
            exportId: export_id,
          },
        }));
        while (true) {
          const s = await getExportStatus(tenantId, export_id);
          setExportMap((prev) => ({
            ...prev,
            [datasetId]: {
              ...prev[datasetId]!,
              sampleCount: s.sample_count,
            },
          }));
          if (s.status === "done") {
            break;
          }
          await new Promise((r) => setTimeout(r, 2000));
        }
        setExportMap((prev) => ({
          ...prev,
          [datasetId]: {
            ...prev[datasetId]!,
            phase: "done",
          },
        }));
        logger.info("export completed", { tenantId, datasetId, export_id });
        return true;
      } catch (e: unknown) {
        const msg = formatApiError(e);
        setExportMap((prev) => ({
          ...prev,
          [datasetId]: {
            phase: "error",
            exportId: null,
            sampleCount: 0,
            errMsg: msg,
          },
        }));
        logger.warn("export failed", { tenantId, datasetId, msg });
        return false;
      }
    },
    [tenantId],
  );

  const handleBulkExportAll = useCallback(async () => {
    const targets = rows.filter((r) => (r.labeled_count ?? 0) > 0);
    if (targets.length === 0) {
      setListErr(null);
      setListMsg("라벨이 있는 데이터셋이 없습니다.");
      return;
    }
    setListErr(null);
    setListMsg(null);
    setBulkExportBusy(true);
    try {
      let ok = 0;
      let fail = 0;
      for (const r of targets) {
        const success = await runExportForDataset(r.dataset_id);
        if (success) {
          ok += 1;
        } else {
          fail += 1;
        }
      }
      setListMsg(
        `전체 내보내기 완료: 성공 ${ok}개${fail > 0 ? ` · 실패 ${fail}개` : ""} (라벨 있는 데이터셋 ${targets.length}개 중)`,
      );
    } finally {
      setBulkExportBusy(false);
    }
  }, [rows, runExportForDataset]);

  const closeImpactModal = useCallback(() => {
    setImpactModalOpen(false);
    setPendingExport(null);
  }, []);

  const openImpactModalSingle = useCallback((datasetId: string) => {
    setPendingExport({ kind: "single", datasetId });
    setImpactModalOpen(true);
  }, []);

  const openImpactModalBulk = useCallback(() => {
    const targets = rows.filter((r) => (r.labeled_count ?? 0) > 0);
    if (targets.length === 0) {
      setListErr(null);
      setListMsg("라벨이 있는 데이터셋이 없습니다.");
      return;
    }
    setPendingExport({ kind: "bulk" });
    setImpactModalOpen(true);
  }, [rows]);

  const confirmImpactExport = useCallback(() => {
    const p = pendingExport;
    if (!p) {
      return;
    }
    setImpactModalOpen(false);
    setPendingExport(null);
    if (p.kind === "single") {
      void runExportForDataset(p.datasetId);
    } else {
      void handleBulkExportAll();
    }
  }, [pendingExport, runExportForDataset, handleBulkExportAll]);

  const handleDeleteDatasetRow = async (datasetId: string) => {
    if (
      !window.confirm(
        `데이터셋 "${datasetId}"을(를) 완전히 삭제할까요?\nDB·타일·마스크·export 폴더가 제거되며 되돌릴 수 없습니다.`,
      )
    ) {
      return;
    }
    setListErr(null);
    setListMsg(null);
    setRowDeleteBusy(datasetId);
    try {
      await deleteDataset(tenantId, datasetId);
      if (selectedDatasetId === datasetId) {
        onSelectDataset("");
      }
      setListMsg(`데이터셋 "${datasetId}" 삭제됨.`);
      await refreshList();
      logger.info("dataset deleted", { tenantId, datasetId });
    } catch (e: unknown) {
      setListErr(formatApiError(e));
    } finally {
      setRowDeleteBusy(null);
    }
  };

  return (
    <main className="page-datasets">
      <header className="page-header">
        <h1>데이터셋 관리</h1>
        <p className="page-sub">
          등록된 데이터셋 목록에서 선택·타일 생성·U-Net Export·라벨링으로 이동합니다. 새 데이터셋 등록·원본 GeoTIFF 연결은
          &quot;새 데이터셋&quot;을 눌러 주세요.
        </p>
      </header>

      <div className="datasets-stack">
        <section className="datasets-panel">
          <h2 className="datasets-panel-title">등록된 데이터셋</h2>
          <div className="datasets-toolbar datasets-toolbar-main">
            <button type="button" className="datasets-open-setup-btn" onClick={openSetupModal}>
              새 데이터셋
            </button>
            <button type="button" onClick={() => void refreshList()} disabled={listLoading}>
              {listLoading ? "목록 로딩…" : "목록 새로고침"}
            </button>
            <button
              type="button"
              className="datasets-bulk-export-btn"
              onClick={() => openImpactModalBulk()}
              disabled={listLoading || bulkExportBusy}
              title="설정 영향도 확인 후 labeled_count가 1 이상인 데이터셋만 순서대로 U-Net ZIP으로 내보냅니다."
            >
              {bulkExportBusy ? "전체 내보내기 중…" : "전체 내보내기"}
            </button>
            <span className="muted datasets-selection-hint">
              선택됨: <code>{selectedDatasetId || "없음"}</code>
            </span>
          </div>
          {listError ? <p className="error">{listError}</p> : null}
          {listMsg ? <p className="datasets-msg">{listMsg}</p> : null}
          {listErr ? <p className="datasets-err">{listErr}</p> : null}

          <div className="datasets-table-wrap datasets-table-scroll">
            <table className="datasets-table">
              <thead>
                <tr>
                  <th>dataset_id</th>
                  <th>원본 GeoTIFF</th>
                  <th>타일</th>
                  <th className="datasets-labeled-head" title="라벨 저장된 타일 수">
                    라벨
                  </th>
                  <th>생성 시각</th>
                  <th className="datasets-export-head">Export</th>
                  <th className="datasets-actions-head">동작</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && !listLoading ? (
                  <tr>
                    <td colSpan={7} className="muted">
                      데이터셋이 없습니다. 상단의 &quot;새 데이터셋&quot;에서 등록하거나, 타일이 필요하면 GeoTIFF를
                      올린 뒤 연결하세요.
                    </td>
                  </tr>
                ) : null}
                {rows.map((r) => {
                  const src = r.source_geotiff?.trim() ?? "";
                  const hasSrc = src.length > 0;
                  const n = r.tile_count ?? 0;
                  const lc = r.labeled_count ?? 0;
                  const exp = exportMap[r.dataset_id];
                  const busy =
                    tileGenRunningId === r.dataset_id ||
                    tileGenQueuedIds.includes(r.dataset_id) ||
                    rowDeleteBusy === r.dataset_id;
                  return (
                    <tr
                      key={r.dataset_id}
                      className={selectedDatasetId === r.dataset_id ? "selected" : ""}
                      onClick={() => onSelectDataset(r.dataset_id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onSelectDataset(r.dataset_id);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                    >
                      <td>
                        <code>{r.dataset_id}</code>
                      </td>
                      <td>{r.source_geotiff ?? "—"}</td>
                      <td className="datasets-tile-cell">
                        {n > 0 ? (
                          <span className="datasets-tile-count">{n}개</span>
                        ) : hasSrc ? (
                          <button
                            type="button"
                            className="datasets-inline-action"
                            disabled={busy}
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleRowGenerateTiles(r.dataset_id, src);
                            }}
                          >
                            {tileGenRunningId === r.dataset_id
                              ? "생성 중…"
                              : tileGenQueuedIds.includes(r.dataset_id)
                                ? "대기 중…"
                                : "타일 생성"}
                          </button>
                        ) : (
                          <span className="muted" title="데이터셋에 원본 파일명이 없습니다.">
                            원본 없음
                          </span>
                        )}
                      </td>
                      <td className="datasets-labeled-cell muted" title="라벨이 저장된 타일 수">
                        {lc > 0 ? <span className="datasets-labeled-count">{lc}</span> : "—"}
                      </td>
                      <td className="muted">{r.created_at}</td>
                      <td
                        className="datasets-export-cell"
                        onClick={(e) => {
                          e.stopPropagation();
                        }}
                      >
                        {lc === 0 ? (
                          <span className="muted">라벨 없음</span>
                        ) : !exp ? (
                          <button
                            type="button"
                            className="datasets-inline-action"
                            disabled={bulkExportBusy}
                            onClick={(e) => {
                              e.stopPropagation();
                              openImpactModalSingle(r.dataset_id);
                            }}
                          >
                            내보내기
                          </button>
                        ) : exp.phase === "exporting" ? (
                          <span className="datasets-export-status">
                            <span className="datasets-export-spinner" aria-hidden />
                            <span className="muted">
                              {exp.exportId ? `처리 중 (${exp.sampleCount}샘플)` : "요청 중…"}
                            </span>
                          </span>
                        ) : exp.phase === "done" && exp.exportId ? (
                          <span className="datasets-export-done">
                            <a
                              className="datasets-export-download"
                              href={getExportDownloadUrl(tenantId, exp.exportId)}
                              download
                            >
                              ZIP 다운로드
                            </a>
                            <button
                              type="button"
                              className="datasets-inline-action"
                              onClick={() => resetExportRow(r.dataset_id)}
                            >
                              닫기
                            </button>
                          </span>
                        ) : (
                          <span className="datasets-export-error-wrap">
                            <span className="datasets-err datasets-export-err-inline" title={exp.errMsg ?? ""}>
                              실패
                            </span>
                            <button
                              type="button"
                              className="datasets-inline-action"
                              onClick={() => resetExportRow(r.dataset_id)}
                            >
                              초기화
                            </button>
                          </span>
                        )}
                      </td>
                      <td className="datasets-actions-cell">
                        <button
                          type="button"
                          className="datasets-goto-label"
                          title="이 데이터셋으로 라벨링"
                          disabled={busy}
                          onClick={(e) => {
                            e.stopPropagation();
                            onGoToLabeling(r.dataset_id);
                          }}
                        >
                          ▶ 라벨링
                        </button>
                        <button
                          type="button"
                          className="datasets-del-btn"
                          title="데이터셋 삭제"
                          disabled={busy}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleDeleteDatasetRow(r.dataset_id);
                          }}
                        >
                          {rowDeleteBusy === r.dataset_id ? "…" : "삭제"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {impactModalOpen ? (
        <div
          className="datasets-modal-backdrop datasets-impact-modal-backdrop"
          role="presentation"
          onClick={() => closeImpactModal()}
        >
          <div
            className="datasets-modal-dialog datasets-impact-modal-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="datasets-impact-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="datasets-modal-header">
              <h2 id="datasets-impact-modal-title">내보내기 · 설정 영향도</h2>
              <button
                type="button"
                className="datasets-modal-close"
                aria-label="닫기"
                onClick={() => closeImpactModal()}
              >
                ×
              </button>
            </header>
            <div className="datasets-modal-body datasets-impact-modal-body">
              <p className="datasets-hint datasets-impact-modal-lead">
                ZIP 생성 전 타일 설정(tile_size / overlap) 변경 시 예상 영향을 확인한 뒤 진행할 수 있습니다.
              </p>
              <ConfigImpactWidget tenantId={tenantId} embedded />
              <div className="datasets-impact-modal-footer">
                <button type="button" onClick={() => closeImpactModal()}>
                  취소
                </button>
                <button
                  type="button"
                  className="datasets-impact-modal-confirm"
                  onClick={() => confirmImpactExport()}
                  disabled={bulkExportBusy}
                >
                  {pendingExport?.kind === "bulk" ? "전체 ZIP 생성" : "ZIP 생성 시작"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {setupModalOpen ? (
        <div
          className="datasets-modal-backdrop"
          role="presentation"
          onClick={() => setSetupModalOpen(false)}
        >
          <div
            className="datasets-modal-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="datasets-setup-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="datasets-modal-header">
              <h2 id="datasets-setup-modal-title">새 데이터셋</h2>
              <button
                type="button"
                className="datasets-modal-close"
                aria-label="닫기"
                onClick={() => setSetupModalOpen(false)}
              >
                ×
              </button>
            </header>
            <div className="datasets-modal-body">
              <section className="datasets-modal-workspace">
                <div className="datasets-modal-workspace-head">
                  <h3 className="datasets-modal-section-title datasets-modal-section-title--primary">
                    데이터셋 등록
                  </h3>
                  <div className="datasets-modal-upload-corner" aria-busy={uploadBusy}>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".tif,.tiff,image/tiff"
                      multiple
                      className="datasets-file-input-hidden"
                      onChange={(e) => void handleGeotiffUpload(e)}
                      disabled={uploadBusy || createBusy}
                    />
                    <button
                      type="button"
                      className="datasets-modal-upload-btn"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploadBusy || createBusy}
                      title="여러 파일 선택 가능 · 서버 raw_geotiff 폴더에 저장 · 같은 이름이면 덮어씁니다."
                    >
                      GeoTIFF 업로드
                    </button>
                    {!uploadBusy ? (
                      <p className="datasets-modal-upload-note">서버 저장 · 동일 파일명 덮어쓰기</p>
                    ) : (
                      <p className="datasets-modal-upload-note datasets-modal-upload-note--busy">
                        진행 상황은 화면 오른쪽 아래를 확인하세요.
                      </p>
                    )}
                  </div>
                </div>

                <div className="datasets-modal-create-block datasets-create-body">
                  <label>
                    새 dataset ID
                    <input
                      value={newDatasetId}
                      onChange={(e) => setNewDatasetId(e.target.value)}
                      placeholder="예: my_yard_v1"
                      disabled={createBusy}
                      autoComplete="off"
                    />
                  </label>
                  <p className="datasets-hint">
                    <strong className="datasets-hint-strong">생성</strong>은 GeoTIFF 없이 등록만 할 수 있습니다.{" "}
                    <strong className="datasets-hint-strong">생성+타일</strong>은 아래 원본 표에서 파일을 고른 뒤
                    누르세요.
                  </p>
                  <div className="datasets-create-actions">
                    <button type="button" onClick={() => void handleCreateOnly()} disabled={createBusy}>
                      생성
                    </button>
                    <button type="button" onClick={() => void handleCreateAndTiles()} disabled={createBusy}>
                      생성+타일
                    </button>
                  </div>
                  {createMsg ? <p className="datasets-msg">{createMsg}</p> : null}
                  {createErr ? <p className="datasets-err">{createErr}</p> : null}
                </div>

                <div className="datasets-modal-list-section">
                  <div className="datasets-modal-list-toolbar">
                    <span className="datasets-modal-list-heading">원본 GeoTIFF</span>
                    <button type="button" onClick={() => void refreshGeotiffs()} disabled={uploadBusy}>
                      목록 새로고침
                    </button>
                  </div>
                  <p className="datasets-hint datasets-modal-list-hint">
                    타일·원본 연결에 쓸 파일을 표에서 선택합니다.
                  </p>
                  <div className="datasets-geotiff-table-wrap datasets-modal-geotiff-scroll">
                    <table className="datasets-geotiff-table">
                      <thead>
                        <tr>
                          <th className="datasets-geotiff-col-select" scope="col">
                            선택
                          </th>
                          <th scope="col">파일명</th>
                          <th className="datasets-geotiff-col-num" scope="col">
                            크기
                          </th>
                          <th className="datasets-geotiff-col-mtime" scope="col">
                            수정 시각
                          </th>
                          <th className="datasets-geotiff-col-actions" scope="col">
                            동작
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {geotiffFiles.length === 0 ? (
                          <tr>
                            <td colSpan={5} className="muted">
                              파일이 없습니다. 상단 오른쪽에서 업로드하거나 목록 새로고침을 눌러 보세요.
                            </td>
                          </tr>
                        ) : (
                          geotiffFiles.map((g) => {
                            const sel = selectedGeotiff === g.filename;
                            return (
                              <tr
                                key={g.filename}
                                className={
                                  "datasets-geotiff-data-row" +
                                  (sel ? " datasets-geotiff-row-selected" : "")
                                }
                                onClick={() => {
                                  if (!createBusy) {
                                    setSelectedGeotiff(g.filename);
                                  }
                                }}
                              >
                                <td className="datasets-geotiff-col-select">
                                  <input
                                    type="radio"
                                    name="dataset-geotiff"
                                    checked={sel}
                                    onChange={() => setSelectedGeotiff(g.filename)}
                                    disabled={createBusy}
                                    onClick={(e) => e.stopPropagation()}
                                    aria-label={`${g.filename}을(를) 원본으로 선택`}
                                  />
                                </td>
                                <td>
                                  <code className="datasets-geotiff-filename">{g.filename}</code>
                                </td>
                                <td className="datasets-geotiff-col-num">{formatBytes(g.size)}</td>
                                <td className="muted datasets-geotiff-col-mtime">{g.mtime}</td>
                                <td className="datasets-geotiff-col-actions">
                                  <button
                                    type="button"
                                    className="datasets-del-btn"
                                    title="파일 삭제"
                                    disabled={geotiffDeleteBusy !== null || createBusy}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      void handleDeleteGeotiffFile(g.filename);
                                    }}
                                  >
                                    {geotiffDeleteBusy === g.filename ? "…" : "삭제"}
                                  </button>
                                </td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </div>
      ) : null}

      {uploadBusy ? (
        <div className="datasets-upload-toast" role="status" aria-live="polite">
          <div className="datasets-upload-toast-inner">
            <span className="datasets-upload-spinner datasets-upload-spinner--toast" aria-hidden />
            <div className="datasets-upload-toast-copy">
              <p className="datasets-upload-toast-title">GeoTIFF 업로드 중</p>
              <p className="datasets-upload-toast-detail">
                {uploadTotal}개 파일 · 평균 진행 {uploadPct ?? 0}%
              </p>
              <p className="datasets-upload-toast-hint">
                완료될 때까지 이 페이지를 벗어나거나 창을 닫지 마세요. 용량에 따라 수 분 걸릴 수 있습니다.
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {tileGenToast ? (
        <div
          className={`datasets-upload-toast datasets-tilegen-toast${uploadBusy ? " datasets-toast--stacked" : ""}`}
          role="status"
          aria-live="polite"
        >
          <div className="datasets-upload-toast-inner">
            <span className="datasets-upload-spinner datasets-upload-spinner--toast" aria-hidden />
            <div className="datasets-upload-toast-copy">
              <p className="datasets-upload-toast-title">타일 생성 중</p>
              <p className="datasets-upload-toast-detail">
                데이터셋 <code>{tileGenToast.datasetId}</code>
              </p>
              <p className="datasets-upload-toast-hint">
                {tileGenToast.queueBehind > 0 ? `앞으로 ${tileGenToast.queueBehind}건이 대기 중입니다. ` : ""}
                GeoTIFF를 읽어 타일 이미지를 만듭니다. 원본 크기에 따라 수 분 걸릴 수 있습니다.
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
