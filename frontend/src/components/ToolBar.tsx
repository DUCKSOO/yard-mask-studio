import type { SamPrompt } from "../api/client";

export type ToolMode = "brush" | "point_pos" | "point_neg" | "box" | "pan";

type ToolBarProps = {
  tool: ToolMode;
  onToolChange: (t: ToolMode) => void;
  prompts: SamPrompt[];
  onClearPrompts: () => void;
  onRunSam: () => void;
  samBusy: boolean;
  samMessage: string | null;
};

export function ToolBar({
  tool,
  onToolChange,
  prompts,
  onClearPrompts,
  onRunSam,
  samBusy,
  samMessage,
}: ToolBarProps) {
  return (
    <div className="tool-bar">
      <h3>도구</h3>
      <div className="tool-buttons">
        {(
          [
            ["brush", "브러시"],
            ["point_pos", "점(+)"],
            ["point_neg", "점(−)"],
            ["box", "박스"],
            ["pan", "이동"],
          ] as const
        ).map(([id, label]) => (
          <button key={id} type="button" className={tool === id ? "active" : ""} onClick={() => onToolChange(id)}>
            {label}
          </button>
        ))}
      </div>
      <p className="hint">휠: 확대/축소 · 중간 버튼 드래그: 이동</p>
      <div className="sam-row">
        <button type="button" disabled={samBusy || prompts.length === 0} onClick={onRunSam}>
          {samBusy ? "SAM…" : "SAM 실행"}
        </button>
        <button type="button" onClick={onClearPrompts}>
          프롬프트 비우기
        </button>
      </div>
      <p className="sam-meta">프롬프트 {prompts.length}개</p>
      {samMessage ? <p className="sam-msg">{samMessage}</p> : null}
    </div>
  );
}
