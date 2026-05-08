import { useCallback, useEffect, useState } from "react";
import { approveReview, getReviewQueue, rejectReview, type ReviewQueueItem } from "../api/client";

type ReviewFilter = "pending" | "approved" | "rejected" | "all";

type ReviewPanelProps = {
  tenantId: string;
};

export function ReviewPanel({ tenantId }: ReviewPanelProps) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<ReviewFilter>("pending");
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejectNotes, setRejectNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const list = await getReviewQueue(tenantId, { status: filter });
      setItems(list);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tenantId, filter]);

  useEffect(() => {
    if (!open) {
      return;
    }
    void load();
  }, [open, load]);

  const onApprove = async (it: ReviewQueueItem) => {
    setError(null);
    try {
      await approveReview(tenantId, it.dataset_id, it.tile_id);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onReject = async (it: ReviewQueueItem) => {
    const key = `${it.dataset_id}/${it.tile_id}`;
    const note = rejectNotes[key]?.trim() || undefined;
    setError(null);
    try {
      await rejectReview(tenantId, it.dataset_id, it.tile_id, note);
      setRejectNotes((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section className="review-panel">
      <button type="button" className="review-panel-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "▼ 검수 큐 숨기기" : "▶ 검수 큐"}
      </button>
      {open ? (
        <div className="review-panel-body">
          <label>
            상태 필터
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as ReviewFilter)}
            >
              <option value="pending">pending</option>
              <option value="approved">approved</option>
              <option value="rejected">rejected</option>
              <option value="all">전체</option>
            </select>
          </label>
          <button type="button" onClick={() => void load()} disabled={loading}>
            {loading ? "로딩…" : "새로고침"}
          </button>
          {error ? <p className="error">{error}</p> : null}
          <ul className="review-queue-list">
            {items.length === 0 && !loading ? <li className="muted">항목 없음</li> : null}
            {items.map((it) => {
              const key = `${it.dataset_id}/${it.tile_id}`;
              return (
                <li key={key} className="review-queue-item">
                  <div className="review-queue-meta">
                    <strong>{it.tile_id}</strong>
                    <span className="muted"> · {it.dataset_id}</span>
                    <div>
                      <span className={`review-status review-status-${it.status}`}>{it.status}</span>
                    </div>
                    {it.note ? <div className="review-note">note: {it.note}</div> : null}
                  </div>
                  <div className="review-queue-actions">
                    <input
                      type="text"
                      placeholder="거부 사유(선택)"
                      value={rejectNotes[key] ?? ""}
                      onChange={(e) =>
                        setRejectNotes((prev) => ({ ...prev, [key]: e.target.value }))
                      }
                    />
                    <div className="review-btns">
                      <button type="button" onClick={() => void onApprove(it)}>
                        승인
                      </button>
                      <button type="button" onClick={() => void onReject(it)}>
                        거부
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
