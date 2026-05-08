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
  brushRadius,
  onBrushRadiusChange,
}: ToolBarProps) {
  return (
    <div className="tool-bar">
      <h3>도구</h3>
      <div className="tool-buttons">
        {(
          [
            ["brush", "브러시"],
            ["eraser", "지우개"],
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
