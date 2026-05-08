import type { TileItem } from "../api/client";

/** 원본 영상 기준 격자 인덱스(0부터). 메타에 x/y/tile_size/overlap 없으면 null */
export function tileGridFromMetadata(meta: Record<string, unknown> | undefined): {
  row: number;
  col: number;
} | null {
  if (!meta || typeof meta !== "object") {
    return null;
  }
  const x = Number(meta.x);
  const y = Number(meta.y);
  const tileSize = Number(meta.tile_size);
  const overlap = Number(meta.overlap);
  if (![x, y, tileSize, overlap].every(Number.isFinite)) {
    return null;
  }
  const stride = tileSize - overlap;
  if (!(stride > 0)) {
    return null;
  }
  const row = Math.round(y / stride);
  const col = Math.round(x / stride);
  if (row < 0 || col < 0) {
    return null;
  }
  return { row, col };
}

/** 작업자용 격자 라벨 (1부터 표기): R3·C12 */
export function formatTileGridLabel(meta: Record<string, unknown> | undefined): string | null {
  const g = tileGridFromMetadata(meta);
  if (!g) {
    return null;
  }
  return `R${g.row + 1}·C${g.col + 1}`;
}

/** 목록 정렬: 격자 행→열, 없으면 tile_id */
export function compareTilesForNavigator(a: TileItem, b: TileItem): number {
  const ga = tileGridFromMetadata(a.metadata);
  const gb = tileGridFromMetadata(b.metadata);
  if (ga && gb) {
    if (ga.row !== gb.row) {
      return ga.row - gb.row;
    }
    if (ga.col !== gb.col) {
      return ga.col - gb.col;
    }
    return a.tile_id.localeCompare(b.tile_id);
  }
  if (ga && !gb) {
    return -1;
  }
  if (!ga && gb) {
    return 1;
  }
  return a.tile_id.localeCompare(b.tile_id);
}
