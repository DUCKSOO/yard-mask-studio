import { useState } from "react";
import { DatasetsPage } from "./components/DatasetsPage";
import { LabelingPage } from "./components/LabelingPage";
import { NavBar, type AppPage } from "./components/NavBar";
import { ReviewPage } from "./components/ReviewPage";
import { AnnotationProvider } from "./stores/annotationStore";
import { ConfigProvider } from "./stores/configStore";

const DEFAULT_TENANT = import.meta.env.VITE_TENANT_ID ?? "default";
const DATASET_ID_FROM_ENV = import.meta.env.VITE_DATASET_ID;
const initialDatasetId =
  typeof DATASET_ID_FROM_ENV === "string" && DATASET_ID_FROM_ENV.trim() !== ""
    ? DATASET_ID_FROM_ENV.trim()
    : "";

function AppShell() {
  const [page, setPage] = useState<AppPage>("datasets");
  const [tenantId] = useState(DEFAULT_TENANT);
  const [datasetId, setDatasetId] = useState(initialDatasetId);

  return (
    <div className="app-shell">
      <header className="app-header app-header-shell">
        <h1>yard-mask-studio</h1>
      </header>
      <NavBar page={page} onPage={setPage} datasetId={datasetId} />
      {page === "datasets" ? (
        <DatasetsPage
          tenantId={tenantId}
          selectedDatasetId={datasetId}
          onSelectDataset={setDatasetId}
          onGoToLabeling={(d) => {
            setDatasetId(d);
            setPage("labeling");
          }}
        />
      ) : null}
      {page === "labeling" ? <LabelingPage tenantId={tenantId} datasetId={datasetId} /> : null}
      {page === "review" ? <ReviewPage tenantId={tenantId} /> : null}
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
