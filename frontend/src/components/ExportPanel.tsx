import axios from "axios";
import { useCallback, useEffect, useState } from "react";
import { getExportDownloadUrl, getExportStatus, triggerExport } from "../api/client";
import { logger } from "../utils/logger";

type Phase = "idle" | "exporting" | "done" | "error";

type ExportPanelProps = {
  tenantId: string;
  datasetId: string | null;
};

function formatApiError(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const d = e.response?.data;
    if (d && typeof d === "object" && "detail" in d) {
      const detail = (d as { detail: unknown }).detail;
      if (typeof detail === "string") {
        return detail;
      }
      if (Array.isArray(detail)) {
        return JSON.stringify(detail);
      }
    }
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

export function ExportPanel({ tenantId, datasetId }: ExportPanelProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [exportId, setExportId] = useState<string | null>(null);
  const [sampleCount, setSampleCount] = useState(0);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const reset = useCallback(() => {
    setPhase("idle");
    setExportId(null);
    setSampleCount(0);
    setErrMsg(null);
  }, []);

  useEffect(() => {
    reset();
  }, [tenantId, datasetId, reset]);

  useEffect(() => {
    if (phase === "done" && exportId) {
      logger.info("export completed", { exportId, sampleCount });
    }
    if (phase === "error" && errMsg) {
      logger.warn("export failed", { errMsg });
    }
  }, [phase, exportId, sampleCount, errMsg]);

  useEffect(() => {
    if (phase !== "exporting" || !exportId) {
      return;
    }
    let cancelled = false;
    const tick = async () => {
      try {
        const s = await getExportStatus(tenantId, exportId);
        if (cancelled) {
          return;
        }
        setSampleCount(s.sample_count);
        if (s.status === "done") {
          setPhase("done");
        }
      } catch (e: unknown) {
        if (cancelled) {
          return;
        }
        setPhase("error");
        setErrMsg(formatApiError(e));
      }
    };
    void tick();
    const intervalId = window.setInterval(tick, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [phase, exportId, tenantId]);

  const handleRun = async () => {
    if (!datasetId?.trim()) {
      return;
    }
    setErrMsg(null);
    setSampleCount(0);
    setExportId(null);
    setPhase("exporting");
    try {
      const { export_id } = await triggerExport(tenantId, datasetId);
      setExportId(export_id);
      logger.info("export started", { tenantId, datasetId, export_id });
    } catch (e: unknown) {
      setPhase("error");
      setErrMsg(formatApiError(e));
    }
  };

  const canRun = Boolean(datasetId?.trim()) && phase !== "exporting";
  const downloadUrl =
    exportId && phase === "done" ? getExportDownloadUrl(tenantId, exportId) : null;

  return (
    <div className="export-panel">
      <h3 className="export-panel-title">U-Net Export</h3>
      <p className="export-panel-hint">라벨된 타일만 ZIP으로 묶어 내보냅니다.</p>
      <button type="button" className="export-panel-run" disabled={!canRun} onClick={() => void handleRun()}>
        {phase === "exporting" ? "처리 중…" : "U-Net Export 실행"}
      </button>
      {phase === "exporting" && !exportId ? (
        <p className="export-panel-status">export 요청 중…</p>
      ) : null}
      {phase === "exporting" && exportId ? (
        <p className="export-panel-status">상태 확인 중… (export_id: {exportId.slice(0, 8)}…)</p>
      ) : null}
      {phase === "done" ? (
        <div className="export-panel-done">
          <p className="export-panel-status">샘플 {sampleCount}개 export 완료</p>
          {downloadUrl ? (
            <a className="export-download-link" href={downloadUrl} download>
              ZIP 다운로드
            </a>
          ) : null}
        </div>
      ) : null}
      {phase === "error" && errMsg ? <p className="export-panel-error">{errMsg}</p> : null}
      {phase === "error" ? (
        <button type="button" className="export-panel-reset" onClick={reset}>
          초기화
        </button>
      ) : null}
    </div>
  );
}
