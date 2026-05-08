import axios from "axios";
import { useEffect, useState } from "react";
import { getConfigImpact, type ConfigImpactResponse } from "../api/client";
import { useConfig } from "../stores/configStore";

type ConfigImpactWidgetProps = {
  tenantId: string;
  /** 모달 등 안쪽에 넣을 때 상단 제목(h3) 숨김 */
  embedded?: boolean;
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

export function ConfigImpactWidget({ tenantId, embedded = false }: ConfigImpactWidgetProps) {
  const { config } = useConfig();
  const [tileSize, setTileSize] = useState("");
  const [tileOverlap, setTileOverlap] = useState("");
  const [result, setResult] = useState<ConfigImpactResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!config) {
      return;
    }
    setTileSize(String(config.tiling.tile_size));
    setTileOverlap(String(config.tiling.tile_overlap));
  }, [config]);

  const run = async () => {
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const ts = tileSize.trim() === "" ? undefined : Number(tileSize);
      const ov = tileOverlap.trim() === "" ? undefined : Number(tileOverlap);
      if (ts !== undefined && !Number.isFinite(ts)) {
        throw new Error("tile_size는 숫자여야 합니다.");
      }
      if (ov !== undefined && !Number.isFinite(ov)) {
        throw new Error("tile_overlap은 숫자여야 합니다.");
      }
      const body: { tile_size?: number; tile_overlap?: number } = {};
      if (ts !== undefined) {
        body.tile_size = Math.floor(ts);
      }
      if (ov !== undefined) {
        body.tile_overlap = Math.floor(ov);
      }
      const res = await getConfigImpact(tenantId, body);
      setResult(res);
    } catch (e: unknown) {
      setError(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`config-impact-widget${embedded ? " config-impact-widget--embedded" : ""}`}>
      {embedded ? null : <h3 className="config-impact-title">설정 영향도</h3>}
      <p className="config-impact-hint">tile_size / overlap 변경 시 예상 타일 수(대략).</p>
      <label className="config-impact-field">
        tile_size
        <input
          type="number"
          min={1}
          value={tileSize}
          onChange={(e) => setTileSize(e.target.value)}
        />
      </label>
      <label className="config-impact-field">
        tile_overlap
        <input
          type="number"
          min={0}
          value={tileOverlap}
          onChange={(e) => setTileOverlap(e.target.value)}
        />
      </label>
      <button type="button" className="config-impact-run" disabled={busy} onClick={() => void run()}>
        {busy ? "분석 중…" : "영향 분석"}
      </button>
      {error ? <p className="config-impact-error">{error}</p> : null}
      {result ? (
        <div className="config-impact-result">
          <p className="config-impact-summary">
            현재 {result.current_tile_count}개 → 예상 {result.simulated_tile_count}개 (Δ {result.delta >= 0 ? "+" : ""}
            {result.delta})
          </p>
          {result.affected_datasets.length > 0 ? (
            <ul className="config-impact-datasets">
              {result.affected_datasets.map((d) => (
                <li key={d.dataset_id}>
                  {d.dataset_id}: {d.tile_count} → {d.simulated_tile_count}
                </li>
              ))}
            </ul>
          ) : (
            <p className="config-impact-muted">등록된 타일 없음</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
