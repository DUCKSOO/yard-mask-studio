type CanvasTopBarProps = {
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onClearPrompts: () => void;
  promptsEmpty: boolean;
  onSave: () => void;
  saveDisabled: boolean;
  onDeleteLabel: () => void;
  deleteLabelDisabled: boolean;
  deleteLabelTitle?: string;
  onRunSam: () => void;
  samBusy: boolean;
  samDisabled: boolean;
  autoSamRun: boolean;
  onAutoSamRunChange: (v: boolean) => void;
  samMessage: string | null;
  canPrevTile: boolean;
  canNextTile: boolean;
  onPrevTile: () => void;
  onNextTile: () => void;
  tileLabel?: string | null;
};

export function CanvasTopBar({
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onClearPrompts,
  promptsEmpty,
  onSave,
  saveDisabled,
  onDeleteLabel,
  deleteLabelDisabled,
  deleteLabelTitle,
  onRunSam,
  samBusy,
  samDisabled,
  autoSamRun,
  onAutoSamRunChange,
  samMessage,
  canPrevTile,
  canNextTile,
  onPrevTile,
  onNextTile,
  tileLabel,
}: CanvasTopBarProps) {
  return (
    <div className="canvas-top-bar" role="toolbar" aria-label="캔버스 작업">
      <div className="canvas-top-bar-group">
        <button
          type="button"
          className="canvas-top-bar-btn"
          onClick={onPrevTile}
          disabled={!canPrevTile}
          title="이전 타일"
          aria-label="이전 타일"
        >
          ◀
        </button>
        {tileLabel ? (
          <span className="canvas-top-bar-tile-label" title={tileLabel}>
            {tileLabel}
          </span>
        ) : null}
        <button
          type="button"
          className="canvas-top-bar-btn"
          onClick={onNextTile}
          disabled={!canNextTile}
          title="다음 타일"
          aria-label="다음 타일"
        >
          ▶
        </button>
      </div>
      <div className="canvas-top-bar-group">
        <button type="button" className="canvas-top-bar-btn" onClick={onUndo} disabled={!canUndo} title="실행 취소">
          Undo
        </button>
        <button type="button" className="canvas-top-bar-btn" onClick={onRedo} disabled={!canRedo} title="다시 실행">
          Redo
        </button>
      </div>
      <div className="canvas-top-bar-group">
        <button
          type="button"
          className="canvas-top-bar-btn"
          onClick={onClearPrompts}
          disabled={promptsEmpty}
          title="프롬프트 비우기"
        >
          프롬프트 비우기
        </button>
        <button type="button" className="canvas-top-bar-btn" onClick={onSave} disabled={saveDisabled} title="저장">
          저장
        </button>
        <button
          type="button"
          className="canvas-top-bar-btn canvas-top-bar-btn-danger"
          onClick={onDeleteLabel}
          disabled={deleteLabelDisabled}
          title={
            deleteLabelTitle ??
            "서버에 저장된 마스크 삭제 후 미라벨로 복구"
          }
        >
          라벨 삭제
        </button>
      </div>
      <div className="canvas-top-bar-group">
        <button
          type="button"
          className="canvas-top-bar-btn canvas-top-bar-btn-primary"
          onClick={onRunSam}
          disabled={samBusy || samDisabled}
          title="SAM 실행"
        >
          {samBusy ? "SAM…" : "SAM 실행"}
        </button>
        <label className="canvas-top-bar-auto">
          <input
            type="checkbox"
            checked={autoSamRun}
            onChange={(e) => onAutoSamRunChange(e.target.checked)}
          />
          SAM 자동
        </label>
      </div>
      {samMessage ? (
        <p className="canvas-top-bar-msg" title={samMessage}>
          {samMessage}
        </p>
      ) : null}
    </div>
  );
}
