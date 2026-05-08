import type { SamPrompt } from "../api/client";

export type ToolMode = "point" | "brush";

type ToolBarProps = {
  tool: ToolMode;
  prompts: SamPrompt[];
  samMessage: string | null;
};

/** 사이드바 — 요약·힌트만 (실제 조작은 캔버스 상단·플로팅 도구) */
export function ToolBar({ tool, prompts, samMessage }: ToolBarProps) {
  const positiveCount = prompts.filter((p) => p.type === "point" && p.label === "positive").length;
  const negativeCount = prompts.filter((p) => p.type === "point" && p.label === "negative").length;
  return (
    <div className="tool-bar tool-bar--sidebar">
      <h3>안내</h3>
      <p className="sam-meta">양성 점 {positiveCount}개 · 음성 점 {negativeCount}개</p>
      {samMessage ? <p className="sam-msg">{samMessage}</p> : null}
      <p className="hint workflow-hint">
        점: 좌클릭 양성(초록) · 우클릭 음성(빨강) → SAM · 브러시: 좌클릭 칠하기 · 우클릭 지우개
      </p>
      <p className="hint">상단 메뉴: Undo / 저장 / SAM 등 · 휠: 확대/축소 · 가운데 버튼 드래그: 이동</p>
      {tool === "brush" ? <p className="hint sidebar-tool-hint">플로팅 패널에서 반경(크기) 조절</p> : null}

      <details className="prompt-debug">
        <summary>고급: 프롬프트 원문</summary>
        <div className="prompt-debug-body">
          <pre className="prompt-debug-pre">
            {prompts.length > 0 ? JSON.stringify(prompts, null, 2) : "(없음)"}
          </pre>
        </div>
      </details>
    </div>
  );
}
