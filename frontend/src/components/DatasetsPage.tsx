import { isAxiosError } from "axios";
import { useCallback, useEffect, useState } from "react";
import {
  createDataset,
  generateTiles,
  listDatasets,
  type DatasetListItem,
} from "../api/client";
import { logger } from "../utils/logger";

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
  onTenantChange: (id: string) => void;
  selectedDatasetId: string;
  onSelectDataset: (id: string) => void;
  onGoToLabeling: (tenantId: string, datasetId: string) => void;
};

export function DatasetsPage({
  tenantId,
  onTenantChange,
  selectedDatasetId,
  onSelectDataset,
  onGoToLabeling,
}: DatasetsPageProps) {
  const [rows, setRows] = useState<DatasetListItem[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [newDatasetId, setNewDatasetId] = useState("");
  const [geotiffName, setGeotiffName] = useState("");
  const [createBusy, setCreateBusy] = useState(false);
  const [createMsg, setCreateMsg] = useState<string | null>(null);
  const [createErr, setCreateErr] = useState<string | null>(null);

  const [tileGeoOverride, setTileGeoOverride] = useState("");
  const [tileBusy, setTileBusy] = useState(false);
  const [tileMsg, setTileMsg] = useState<string | null>(null);
  const [tileErr, setTileErr] = useState<string | null>(null);

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

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

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
      const geo = geotiffName.trim();
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
    const geo = geotiffName.trim();
    if (!geo) {
      setCreateErr("타일 생성에는 GeoTIFF 파일명이 필요합니다.");
      return;
    }
    setCreateErr(null);
    setCreateMsg(null);
    setCreateBusy(true);
    try {
      const { dataset_id } = await createDataset(tenantId, id, geo);
      const { tiles_created } = await generateTiles(tenantId, dataset_id, geo);
      setCreateMsg(`데이터셋 "${dataset_id}" 생성 · 타일 ${tiles_created}개 생성됨.`);
      onSelectDataset(dataset_id);
      await refreshList();
      logger.info("dataset created with tiles", { tenantId, dataset_id, tiles_created });
    } catch (e: unknown) {
      setCreateErr(formatApiError(e));
    } finally {
      setCreateBusy(false);
    }
  };

  const handleGenerateTiles = async () => {
    const ds = selectedDatasetId.trim();
    if (!ds) {
      setTileErr("목록에서 데이터셋을 선택하세요.");
      return;
    }
    const row = rows.find((r) => r.dataset_id === ds);
    const override = tileGeoOverride.trim();
    const fallback = row?.source_geotiff?.trim() ?? "";
    if (!override && !fallback) {
      setTileErr("GeoTIFF 파일명이 없습니다. 아래에 파일명을 입력하거나 데이터셋에 source를 등록하세요.");
      return;
    }
    setTileErr(null);
    setTileMsg(null);
    setTileBusy(true);
    try {
      const { tiles_created } = await generateTiles(tenantId, ds, override || fallback);
      setTileMsg(`타일 ${tiles_created}개 생성됨.`);
      await refreshList();
      logger.info("tiles generated", { tenantId, datasetId: ds, tiles_created });
    } catch (e: unknown) {
      setTileErr(formatApiError(e));
    } finally {
      setTileBusy(false);
    }
  };

  const selectedRow = rows.find((r) => r.dataset_id === selectedDatasetId);

  return (
    <main className="page-datasets">
      <header className="page-header">
        <h1>데이터셋 관리</h1>
        <p className="page-sub">
          목록에서 선택한 데이터셋이 상단 내비의 &quot;작업 대상&quot;에 반영됩니다. 라벨링은 [▶] 또는 라벨링 탭으로
          이동하세요.
        </p>
      </header>

      <section className="datasets-section">
        <label className="datasets-tenant">
          Tenant
          <input
            value={tenantId}
            onChange={(e) => onTenantChange(e.target.value)}
            autoComplete="off"
          />
        </label>
        <div className="datasets-toolbar">
          <button type="button" onClick={() => void refreshList()} disabled={listLoading}>
            {listLoading ? "목록 로딩…" : "목록 새로고침"}
          </button>
        </div>
        {listError ? <p className="error">{listError}</p> : null}

        <div className="datasets-table-wrap">
          <table className="datasets-table">
            <thead>
              <tr>
                <th>dataset_id</th>
                <th>source_geotiff</th>
                <th>생성 시각</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && !listLoading ? (
                <tr>
                  <td colSpan={4} className="muted">
                    데이터셋이 없습니다. 아래에서 새로 만드세요.
                  </td>
                </tr>
              ) : null}
              {rows.map((r) => (
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
                  <td className="muted">{r.created_at}</td>
                  <td className="datasets-actions-cell">
                    <button
                      type="button"
                      className="datasets-goto-label"
                      title="이 데이터셋으로 라벨링"
                      onClick={(e) => {
                        e.stopPropagation();
                        onGoToLabeling(tenantId, r.dataset_id);
                      }}
                    >
                      ▶ 라벨링
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="datasets-section">
        <h2>선택된 데이터셋 · 타일 생성</h2>
        <p className="muted">
          선택: <code>{selectedDatasetId || "없음"}</code>
          {selectedRow?.source_geotiff ? (
            <>
              {" "}
              · 등록된 GeoTIFF: <code>{selectedRow.source_geotiff}</code>
            </>
          ) : null}
        </p>
        <label>
          이번 실행만 다른 GeoTIFF 파일명 (선택)
          <input
            value={tileGeoOverride}
            onChange={(e) => setTileGeoOverride(e.target.value)}
            placeholder="비우면 데이터셋에 저장된 파일명 사용"
            autoComplete="off"
          />
        </label>
        <button
          type="button"
          disabled={tileBusy || !selectedDatasetId.trim()}
          onClick={() => void handleGenerateTiles()}
        >
          {tileBusy ? "타일 생성 중…" : "타일 생성"}
        </button>
        {tileMsg ? <p className="datasets-msg">{tileMsg}</p> : null}
        {tileErr ? <p className="datasets-err">{tileErr}</p> : null}
      </section>

      <section className="datasets-section datasets-create">
        <button
          type="button"
          className="datasets-create-toggle"
          aria-expanded={createOpen}
          onClick={() => setCreateOpen((v) => !v)}
        >
          {createOpen ? "▼" : "▶"} 새 데이터셋 생성
        </button>
        {createOpen ? (
          <div className="datasets-create-body">
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
            <label>
              GeoTIFF 파일명만
              <input
                value={geotiffName}
                onChange={(e) => setGeotiffName(e.target.value)}
                placeholder="raw_geotiff 폴더 내 파일명"
                disabled={createBusy}
                autoComplete="off"
              />
            </label>
            <p className="datasets-hint">
              경로 없이 파일명만 입력합니다. 예: <code>synthetic_step3.tif</code>
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
        ) : null}
      </section>
    </main>
  );
}
