import { ConfigImpactWidget } from "./ConfigImpactWidget";
import { ExportPanel } from "./ExportPanel";

type ExportPageProps = {
  tenantId: string;
  datasetId: string;
};

export function ExportPage({ tenantId, datasetId }: ExportPageProps) {
  return (
    <main className="page-export">
      <header className="page-header">
        <h1>Export</h1>
        <p className="page-sub">
          U-Net용 ZIP과 설정 영향도 분석입니다. 내보낼 데이터셋은 상단 내비 <strong>작업 대상</strong>과 동일합니다.
          변경은 <strong>데이터셋</strong> 탭에서 하세요.
        </p>
      </header>
      <section className="export-page-section">
        <ExportPanel tenantId={tenantId} datasetId={datasetId} />
      </section>
      <section className="export-page-section">
        <h2 className="export-page-h2">설정 영향도</h2>
        <ConfigImpactWidget tenantId={tenantId} />
      </section>
    </main>
  );
}
