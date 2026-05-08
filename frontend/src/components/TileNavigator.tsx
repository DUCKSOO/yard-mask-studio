import { useMemo, useState } from "react";

export type TileFilter = "all" | "unlabeled" | "labeled" | "approved" | "rejected";

export type TileNavItem = { tile_id: string; status: string };

const STATUS_CLASS: Record<string, string> = {
  unlabeled: "tile-unlabeled",
  labeled: "tile-labeled",
  approved: "tile-approved",
  rejected: "tile-rejected",
};

function statusClass(status: string): string {
  return STATUS_CLASS[status] ?? "tile-unknown";
}

/** 긴 tile_id는 그리드에서 축약 표시 (전체는 title 툴팁) */
function shortId(tileId: string): string {
  if (tileId.length <= 14) return tileId;
  return `…${tileId.slice(-12)}`;
}

type TileNavigatorProps = {
  tiles: TileNavItem[];
  selectedTileId: string | null;
  onSelect: (id: string) => void;
};

const TABS: { id: TileFilter; label: string }[] = [
  { id: "all", label: "전체" },
  { id: "unlabeled", label: "미라벨" },
  { id: "labeled", label: "labeled" },
  { id: "approved", label: "approved" },
  { id: "rejected", label: "rejected" },
];

export function TileNavigator({ tiles, selectedTileId, onSelect }: TileNavigatorProps) {
  const [activeFilter, setActiveFilter] = useState<TileFilter>("all");

  const stats = useMemo(() => {
    const counts = {
      total: tiles.length,
      unlabeled: 0,
      labeled: 0,
      approved: 0,
      rejected: 0,
      other: 0,
    };
    for (const t of tiles) {
      if (t.status === "unlabeled") counts.unlabeled += 1;
      else if (t.status === "labeled") counts.labeled += 1;
      else if (t.status === "approved") counts.approved += 1;
      else if (t.status === "rejected") counts.rejected += 1;
      else counts.other += 1;
    }
    return counts;
  }, [tiles]);

  const tabCounts: Record<TileFilter, number> = useMemo(
    () => ({
      all: stats.total,
      unlabeled: stats.unlabeled,
      labeled: stats.labeled,
      approved: stats.approved,
      rejected: stats.rejected,
    }),
    [stats],
  );

  const filtered = useMemo(() => {
    if (activeFilter === "all") return tiles;
    return tiles.filter((t) => t.status === activeFilter);
  }, [tiles, activeFilter]);

  return (
    <div className="tile-navigator">
      <h3 className="tile-navigator-title">타일</h3>
      <div className="tile-stats" role="status" aria-live="polite">
        <span className="tile-stat">전체 {stats.total}</span>
        <span className="tile-stat tile-stat-unlabeled">미라벨 {stats.unlabeled}</span>
        <span className="tile-stat tile-stat-labeled">labeled {stats.labeled}</span>
        <span className="tile-stat tile-stat-approved">approved {stats.approved}</span>
        <span className="tile-stat tile-stat-rejected">rejected {stats.rejected}</span>
        {stats.other > 0 ? <span className="tile-stat tile-stat-other">기타 {stats.other}</span> : null}
      </div>
      <div className="tile-filter-tabs" role="tablist" aria-label="타일 상태 필터">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeFilter === tab.id}
            className={activeFilter === tab.id ? "active" : ""}
            onClick={() => setActiveFilter(tab.id)}
          >
            {tab.label} ({tabCounts[tab.id]})
          </button>
        ))}
      </div>
      <div className="tile-grid" role="listbox" aria-label="타일 목록">
        {filtered.length === 0 ? (
          <p className="tile-grid-empty">해당 상태의 타일이 없습니다.</p>
        ) : (
          filtered.map((t) => (
            <button
              key={t.tile_id}
              type="button"
              role="option"
              aria-selected={selectedTileId === t.tile_id}
              title={`${t.tile_id} — ${t.status}`}
              className={`tile-btn ${statusClass(t.status)}${selectedTileId === t.tile_id ? " selected" : ""}`}
              onClick={() => onSelect(t.tile_id)}
            >
              <span className="tile-btn-id">{shortId(t.tile_id)}</span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
