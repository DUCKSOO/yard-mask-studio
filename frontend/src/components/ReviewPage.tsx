import { ReviewPanel } from "./ReviewPanel";

type ReviewPageProps = {
  tenantId: string;
};

export function ReviewPage({ tenantId }: ReviewPageProps) {
  return (
    <main className="page-review">
      <header className="page-header">
        <h1>검수</h1>
        <p className="page-sub">
          검수 큐입니다. 타일별 승인·거부는 아래에서 처리합니다.
        </p>
      </header>
      <ReviewPanel tenantId={tenantId} layout="full" />
    </main>
  );
}
