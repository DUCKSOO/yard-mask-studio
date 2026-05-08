export type AppPage = "datasets" | "labeling" | "review" | "export";

type NavBarProps = {
  page: AppPage;
  onPage: (p: AppPage) => void;
  datasetId: string;
};

const TABS: { id: AppPage; label: string }[] = [
  { id: "datasets", label: "데이터셋" },
  { id: "labeling", label: "라벨링" },
  { id: "review", label: "검수" },
  { id: "export", label: "Export" },
];

export function NavBar({ page, onPage, datasetId }: NavBarProps) {
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
      <div className="app-nav-context" title="라벨링·Export·검수에 사용되는 데이터셋">
        <span className="app-nav-context-label">선택 데이터셋</span>
        <code className="app-nav-context-value">{datasetId || "—"}</code>
      </div>
    </nav>
  );
}
