import type { LabelingConfig } from "../api/client";

type ClassPanelProps = {
  config: LabelingConfig | null;
  selectedClassId: number;
  onSelect: (classId: number) => void;
};

/** 라벨링에 쓰는 클래스(0,1,255 등) 선택 — definitions 순서대로 버튼 */
export function ClassPanel({ config, selectedClassId, onSelect }: ClassPanelProps) {
  const defs = config?.classes.definitions ?? [];
  return (
    <div className="class-panel">
      <h3>클래스</h3>
      <div className="class-buttons">
        {defs.map((d) => (
          <button
            key={d.id}
            type="button"
            className={selectedClassId === d.id ? "active" : ""}
            onClick={() => onSelect(d.id)}
            style={{ borderLeft: `4px solid ${d.color}` }}
          >
            {d.name} ({d.id})
          </button>
        ))}
      </div>
    </div>
  );
}
