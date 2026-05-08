import { Circle, Group, Rect } from "react-konva";
import type { SamPrompt } from "../api/client";

type PromptOverlayProps = {
  prompts: SamPrompt[];
};

const POINT_RADIUS = 6;

/** SAM 프롬프트(점·박스) 시각화 — 항상 listening=false로 마스크·히트 영역 아래에 두지 않고, 마스크 위에 올려 표시 */
export function PromptOverlay({ prompts }: PromptOverlayProps) {
  return (
    <Group listening={false}>
      {prompts.map((p, i) => {
        if (p.type === "point") {
          const positive = p.label === "positive";
          return (
            <Circle
              key={`prompt-${i}-${p.x}-${p.y}-pt`}
              x={p.x}
              y={p.y}
              radius={POINT_RADIUS}
              fill={positive ? "#22c55e" : "#ef4444"}
              stroke="#ffffff"
              strokeWidth={2}
              shadowColor="rgba(0,0,0,0.45)"
              shadowBlur={3}
              shadowOffset={{ x: 0, y: 1 }}
            />
          );
        }
        return (
          <Rect
            key={`prompt-${i}-box`}
            x={p.x1}
            y={p.y1}
            width={p.x2 - p.x1}
            height={p.y2 - p.y1}
            stroke="#3b82f6"
            strokeWidth={2}
            fill="rgba(59,130,246,0.12)"
          />
        );
      })}
    </Group>
  );
}
