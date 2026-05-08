export type AppPage = "datasets" | "labeling" | "review" | "export";

type NavBarProps = {
  page: AppPage;
  onPage: (p: AppPage) => void;
  tenantId: string;
  datasetId: string;
};

const TABS: { id: AppPage; label: string }[] = [
  { id: "datasets", label: "데이터셋" },
  { id: "labeling", label: "라벨링" },
  { id: "review", label: "검수" },
  { id: "export", label: "Export" },
];

export function NavBar({ page, onPage, tenantId, datasetId }: NavBarProps) {
  const noDataset = !datasetId.trim();
  return (
    <nav className="app-nav" aria-label="주요 화면">
      <div className="app-nav-tabs">
        {TABS.map((t) => {
          const labelingLocked = t.id === "labeling" && noDataset;
          return (
          <button
            key={t.id}
            type="button"
            disabled={labelingLocked}
            title={labelingLocked ? "데이터셋을 먼저 선택하세요" : undefined}
            className={`app-nav-tab ${page === t.id ? "active" : ""}`}
            onClick={() => onPage(t.id)}
          >
            {t.label}
          </button>
          );
        })}
      </div>
      <div className="app-nav-context" title="라벨링·Export·검수에 사용되는 작업 대상">
        <span className="app-nav-context-label">작업 대상</span>
        <code className="app-nav-context-value">
          {tenantId} / {datasetId || "—"}
        </code>
      </div>
    </nav>
  );
}
