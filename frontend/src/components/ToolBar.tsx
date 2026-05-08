import type { SamPrompt } from "../api/client";

export type ToolMode = "brush" | "eraser" | "point_pos" | "point_neg" | "box" | "pan";

type ToolBarProps = {
  tool: ToolMode;
  onToolChange: (t: ToolMode) => void;
  prompts: SamPrompt[];
  onClearPrompts: () => void;
  onRunSam: () => void;
  samBusy: boolean;
  samMessage: string | null;
  autoSamRun: boolean;
  onAutoSamRunChange: (v: boolean) => void;
  brushRadius: number;
  onBrushRadiusChange: (r: number) => void;
};

export function ToolBar({
  tool,
  onToolChange,
  prompts,
  onClearPrompts,
  onRunSam,
  samBusy,
  samMessage,
  autoSamRun,
  onAutoSamRunChange,
  brushRadius,
  onBrushRadiusChange,
}: ToolBarProps) {
  const samPromptButtons = (
    [
      ["point_pos", "점(+)"],
      ["point_neg", "점(−)"],
      ["box", "박스"],
    ] as const
  ).map(([id, label]) => (
    <button key={id} type="button" className={tool === id ? "active" : ""} onClick={() => onToolChange(id)}>
      {label}
    </button>
  ));

  const directEditButtons = (
    [
      ["brush", "브러시"],
      ["eraser", "지우개"],
      ["pan", "이동"],
    ] as const
  ).map(([id, label]) => (
    <button key={id} type="button" className={tool === id ? "active" : ""} onClick={() => onToolChange(id)}>
      {label}
    </button>
  ));

  return (
    <div className="tool-bar">
      <h3>도구</h3>

      <small className="tool-group-label">SAM 프롬프트</small>
      <div className="tool-group">
        <div className="tool-buttons">{samPromptButtons}</div>
        <div className="sam-row">
          <button type="button" disabled={samBusy || prompts.length === 0} onClick={onRunSam}>
            {samBusy ? "SAM…" : "SAM 실행"}
          </button>
          <button type="button" onClick={onClearPrompts}>
            프롬프트 비우기
          </button>
        </div>
        <label className="auto-sam-toggle">
          <input
            type="checkbox"
            checked={autoSamRun}
            onChange={(e) => onAutoSamRunChange(e.target.checked)}
          />
          프롬프트 추가 후 SAM 자동 실행
        </label>
        <p className="sam-meta">프롬프트 {prompts.length}개</p>
        {samMessage ? <p className="sam-msg">{samMessage}</p> : null}
      </div>

      <small className="tool-group-label">직접 편집</small>
      <div className="tool-group">
        <div className="tool-buttons">{directEditButtons}</div>
        {tool === "brush" || tool === "eraser" ? (
          <div className="brush-radius-row">
            <label className="brush-radius-label">
              반경 {brushRadius}px
              <input
                type="range"
                min={2}
                max={80}
                step={1}
                value={brushRadius}
                onChange={(e) => onBrushRadiusChange(Number(e.target.value))}
              />
            </label>
          </div>
        ) : null}
      </div>

      <p className="hint workflow-hint">
        권장 순서: 점(+) 클릭
        {autoSamRun ? " (자동 SAM)" : " → SAM 실행"}
        {" → "}
        필요 시 브러시로 수정 · 우클릭: 점 모드에서 제외 점, 브러시 모드에서 지우개
      </p>
      <p className="hint">휠: 확대/축소 · 중간 버튼 드래그: 이동</p>
    </div>
  );
}
