import { Group, Line } from "react-konva";

type GridOverlayProps = {
  width: number;
  height: number;
  gridPixelX: number;
  gridPixelY: number;
};

/** source_image_top_left 기준 격자 (픽셀 간격) */
export function GridOverlay({ width, height, gridPixelX, gridPixelY }: GridOverlayProps) {
  if (gridPixelX <= 0 || gridPixelY <= 0) {
    return null;
  }
  const vLines: JSX.Element[] = [];
  for (let x = 0; x <= width; x += gridPixelX) {
    vLines.push(<Line key={`v-${x}`} points={[x, 0, x, height]} stroke="rgba(255,255,255,0.35)" strokeWidth={1} listening={false} />);
  }
  const hLines: JSX.Element[] = [];
  for (let y = 0; y <= height; y += gridPixelY) {
    hLines.push(<Line key={`h-${y}`} points={[0, y, width, y]} stroke="rgba(255,255,255,0.35)" strokeWidth={1} listening={false} />);
  }
  return (
    <Group listening={false}>
      {vLines}
      {hLines}
    </Group>
  );
}
