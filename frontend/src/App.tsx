import { useState } from "react";
import { DatasetsPage } from "./components/DatasetsPage";
import { ExportPage } from "./components/ExportPage";
import { LabelingPage } from "./components/LabelingPage";
import { NavBar, type AppPage } from "./components/NavBar";
import { ReviewPage } from "./components/ReviewPage";
import { AnnotationProvider } from "./stores/annotationStore";
import { ConfigProvider } from "./stores/configStore";

const DEFAULT_TENANT = import.meta.env.VITE_TENANT_ID ?? "default";
const DEFAULT_DATASET = import.meta.env.VITE_DATASET_ID ?? "step3_e2e";

function AppShell() {
  const [page, setPage] = useState<AppPage>("datasets");
  const [tenantId, setTenantId] = useState(DEFAULT_TENANT);
  const [datasetId, setDatasetId] = useState(DEFAULT_DATASET);

  return (
    <div className="app-shell">
      <header className="app-header app-header-shell">
        <h1>yard-mask-studio</h1>
      </header>
      <NavBar page={page} onPage={setPage} tenantId={tenantId} datasetId={datasetId} />
      {page === "datasets" ? (
        <DatasetsPage
          tenantId={tenantId}
          onTenantChange={setTenantId}
          selectedDatasetId={datasetId}
          onSelectDataset={setDatasetId}
          onGoToLabeling={(t, d) => {
            setTenantId(t);
            setDatasetId(d);
            setPage("labeling");
          }}
        />
      ) : null}
      {page === "labeling" ? <LabelingPage tenantId={tenantId} datasetId={datasetId} /> : null}
      {page === "review" ? <ReviewPage tenantId={tenantId} /> : null}
      {page === "export" ? <ExportPage tenantId={tenantId} datasetId={datasetId} /> : null}
    </div>
  );
}

export default function App() {
  return (
    <ConfigProvider>
      <AnnotationProvider>
        <AppShell />
      </AnnotationProvider>
    </ConfigProvider>
  );
}
