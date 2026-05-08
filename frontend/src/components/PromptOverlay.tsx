import { Circle, Group, Rect } from "react-konva";
import type { SamPrompt } from "../api/client";

type PromptOverlayProps = {
  prompts: SamPrompt[];
  /** Stage 내 뷰 Group의 scale — 전달 시 화면에서 점/선 두께를 일정하게 유지 */
  viewScale?: number;
};

const BASE_SCREEN_POINT_PX = 6;

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

/** 화면 기준 px 크기를 이미지 좌표 반경으로 환산 (부모 Group에 viewScale이 곱해짐) */
function radiusInImageForScreenPx(screenPx: number, viewScale: number): number {
  const s = Math.max(viewScale, 0.05);
  return clamp(screenPx / s, 0.4, 200);
}

function strokeInImageForScreenPx(screenPx: number, viewScale: number): number {
  const s = Math.max(viewScale, 0.05);
  return Math.max(screenPx / s, 0.15);
}

/** SAM 프롬프트(점·박스) 시각화 — 양성: 초록, 음성: 빨강 */
export function PromptOverlay({ prompts, viewScale = 1 }: PromptOverlayProps) {
  const z = viewScale;
  const pointR = radiusInImageForScreenPx(BASE_SCREEN_POINT_PX, z);
  const sw = strokeInImageForScreenPx(2, z);
  const blur = Math.max(3 / z, 0.5);
  const shadowY = Math.max(1 / z, 0.2);

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
              radius={pointR}
              fill={positive ? "#22c55e" : "#ef4444"}
              stroke="#ffffff"
              strokeWidth={sw}
              shadowColor="rgba(0,0,0,0.45)"
              shadowBlur={blur}
              shadowOffset={{ x: 0, y: shadowY }}
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
            strokeWidth={sw}
            fill="rgba(59,130,246,0.12)"
          />
        );
      })}
    </Group>
  );
}
