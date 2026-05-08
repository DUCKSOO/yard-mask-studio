import axios, { type AxiosInstance } from "axios";
import { z } from "zod";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "";

export const api: AxiosInstance = axios.create({
  baseURL,
  timeout: 120_000,
});

const TilingConfigSchema = z.object({
  tile_size: z.number(),
  tile_overlap: z.number(),
  nodata_skip_threshold: z.number(),
  edge_padding_strategy: z.enum(["zero", "reflect", "drop"]),
});

const GeoConfigSchema = z.object({
  expected_gsd_cm: z.number(),
  gsd_tolerance: z.number(),
  manual_gsd_cm: z.number().nullable().optional(),
  default_crs: z.string(),
});

const GridConfigSchema = z.object({
  size_meters: z.number(),
  origin: z.enum(["source_image_top_left", "geo_origin", "tile_top_left"]),
});

const SamConfigSchema = z.object({
  model_variant: z.enum(["hiera_large", "hiera_base"]),
  multimask_output: z.boolean(),
  max_candidates: z.number(),
});

const MaskClassDefinitionSchema = z.object({
  id: z.number(),
  name: z.string(),
  color: z.string(),
});

const ClassesConfigSchema = z.object({
  schema_version: z.string(),
  definitions: z.array(MaskClassDefinitionSchema),
});

const SplitRatioSchema = z.object({
  train: z.number(),
  val: z.number(),
  test: z.number(),
});

const DatasetConfigSchema = z.object({
  output_root: z.string(),
  split_ratio: SplitRatioSchema,
  image_format: z.literal("png"),
  mask_format: z.literal("png"),
});

export const LabelingConfigSchema = z.object({
  tiling: TilingConfigSchema,
  geo: GeoConfigSchema,
  grid: GridConfigSchema,
  sam: SamConfigSchema,
  classes: ClassesConfigSchema,
  dataset: DatasetConfigSchema,
});

export type LabelingConfig = z.infer<typeof LabelingConfigSchema>;

export const TileItemSchema = z.object({
  tile_id: z.string(),
  status: z.string(),
  metadata: z.record(z.string(), z.unknown()),
});

export type TileItem = z.infer<typeof TileItemSchema>;

export const SamPredictResponseSchema = z.object({
  tile_id: z.string(),
  candidates: z.number(),
  mask_shape: z.array(z.number()),
});

export type SamPredictResponse = z.infer<typeof SamPredictResponseSchema>;

export const ClassMaskRLESchema = z.object({
  height: z.number(),
  width: z.number(),
  counts: z.string(),
});

export const AnnotationSaveBodySchema = z.object({
  status: z.string(),
  mask_encoding: z.literal("rle"),
  class_mask: ClassMaskRLESchema,
});

export type AnnotationSaveBody = z.infer<typeof AnnotationSaveBodySchema>;

/** GET annotation 응답 — 저장 시 직렬화된 payload */
export const AnnotationRecordSchema = z.object({
  status: z.string(),
  mask_encoding: z.literal("rle"),
  class_mask: ClassMaskRLESchema,
});

export type AnnotationRecord = z.infer<typeof AnnotationRecordSchema>;

export const ReviewQueueItemSchema = z.object({
  tile_id: z.string(),
  dataset_id: z.string(),
  status: z.string(),
  note: z.string().nullable(),
  created_at: z.string(),
});

export type ReviewQueueItem = z.infer<typeof ReviewQueueItemSchema>;

export async function getConfig(): Promise<LabelingConfig> {
  const { data } = await api.get("/api/config");
  return LabelingConfigSchema.parse(data);
}

export async function getTiles(
  tenantId: string,
  datasetId: string,
  opts?: { status?: string; limit?: number },
): Promise<TileItem[]> {
  const params: Record<string, string | number> = { limit: opts?.limit ?? 200 };
  if (opts?.status !== undefined) {
    params.status = opts.status;
  }
  const { data } = await api.get(`/api/tenants/${tenantId}/datasets/${datasetId}/tiles`, {
    params,
  });
  return z.array(TileItemSchema).parse(data);
}

export function getTileImageUrl(tenantId: string, datasetId: string, tileId: string): string {
  const path = `/api/tenants/${tenantId}/datasets/${datasetId}/tiles/${encodeURIComponent(tileId)}/image`;
  if (baseURL) {
    return `${baseURL.replace(/\/$/, "")}${path}`;
  }
  return path;
}

export async function getTileMetadata(
  tenantId: string,
  datasetId: string,
  tileId: string,
): Promise<Record<string, unknown>> {
  const { data } = await api.get(
    `/api/tenants/${tenantId}/datasets/${datasetId}/tiles/${encodeURIComponent(tileId)}/metadata`,
  );
  return z.record(z.string(), z.unknown()).parse(data);
}

export type SamPrompt =
  | { type: "point"; x: number; y: number; label: "positive" | "negative" }
  | { type: "box"; x1: number; y1: number; x2: number; y2: number };

export async function samPredict(
  tenantId: string,
  datasetId: string,
  tileId: string,
  prompts: SamPrompt[],
  multimaskOutput?: boolean,
): Promise<SamPredictResponse> {
  const { data } = await api.post(
    `/api/tenants/${tenantId}/datasets/${datasetId}/tiles/${encodeURIComponent(tileId)}/sam/predict`,
    { prompts, multimask_output: multimaskOutput },
  );
  return SamPredictResponseSchema.parse(data);
}

export async function saveAnnotation(
  tenantId: string,
  datasetId: string,
  tileId: string,
  body: AnnotationSaveBody,
): Promise<{ saved: boolean; mask_path: string }> {
  const { data } = await api.post(
    `/api/tenants/${tenantId}/datasets/${datasetId}/tiles/${encodeURIComponent(tileId)}/annotation`,
    body,
  );
  return z.object({ saved: z.boolean(), mask_path: z.string() }).parse(data);
}

export async function getAnnotation(
  tenantId: string,
  datasetId: string,
  tileId: string,
): Promise<AnnotationRecord | null> {
  try {
    const { data } = await api.get(
      `/api/tenants/${tenantId}/datasets/${datasetId}/tiles/${encodeURIComponent(tileId)}/annotation`,
    );
    return AnnotationRecordSchema.parse(data);
  } catch (e: unknown) {
    if (axios.isAxiosError(e) && e.response?.status === 404) {
      return null;
    }
    throw e;
  }
}

export async function getReviewQueue(
  tenantId: string,
  opts?: { status?: string },
): Promise<ReviewQueueItem[]> {
  const params: Record<string, string> = {};
  if (opts?.status !== undefined) {
    params.status = opts.status;
  }
  const { data } = await api.get(`/api/tenants/${tenantId}/review/queue`, { params });
  return z.array(ReviewQueueItemSchema).parse(data);
}

export async function approveReview(
  tenantId: string,
  datasetId: string,
  tileId: string,
): Promise<{ ok: boolean; status: string }> {
  const { data } = await api.post(
    `/api/tenants/${tenantId}/datasets/${datasetId}/tiles/${encodeURIComponent(tileId)}/review/approve`,
  );
  return z.object({ ok: z.boolean(), status: z.string() }).parse(data);
}

export async function rejectReview(
  tenantId: string,
  datasetId: string,
  tileId: string,
  note?: string,
): Promise<{ ok: boolean; status: string }> {
  const { data } = await api.post(
    `/api/tenants/${tenantId}/datasets/${datasetId}/tiles/${encodeURIComponent(tileId)}/review/reject`,
    { note: note ?? null },
  );
  return z.object({ ok: z.boolean(), status: z.string() }).parse(data);
}
