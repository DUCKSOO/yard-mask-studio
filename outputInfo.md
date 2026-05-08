# Yard Mask Studio — 내보내기 결과물 명세 (U-Net 학습용)

## 1. 디렉터리 구조

```
data/exports/{tenant_id}/{dataset_id}/{export_id}/
├── images/
├── masks/
├── splits/
│   ├── train.json
│   ├── val.json
│   ├── test.json
│   └── source_groups.json       ← 키: source_image_id
├── tiles_manifest.json
├── sources_catalog.json         ← 선택: source_image_id별 이름·SHA-256 요약 (중복 제거용)
├── mask_schema.json
├── validation_report.json      ← 학습 전 자동 점검 요약
├── classes.json
├── config_snapshot.yaml
└── dataset_manifest.json
```

---

## 2. 이미지 (images/)

| 항목 | 값 |
|------|-----|
| 포맷 | PNG |
| 색상 모드 | RGB (3채널) |
| 크기 | `tile_size × tile_size` px (기본 **1024 × 1024**) |
| 픽셀값 범위 | 0–255 (uint8) |

---

## 3. 마스크 (masks/)

| 항목 | 값 |
|------|-----|
| 포맷 | PNG, 모드 L |
| 크기 | 이미지와 동일 |
| 픽셀값 | **0** = 배경, **255** = occupied |

### mask_schema.json

```json
{
  "task_type": "binary_segmentation",
  "mask_encoding": "binary_0_255",
  "background_value": 0,
  "foreground_value": 255,
  "ignore_value": null
}
```

---

## 4. 클래스 정의 (classes.json)

`id`(내부 클래스 인덱스)와 `mask_value`(export PNG 픽셀값) 분리:

```json
{
  "schema_version": "1.0",
  "definitions": [
    { "id": 0, "name": "non_occupied", "mask_value": 0 },
    { "id": 1, "name": "occupied",     "mask_value": 255 }
  ],
  "ignore_value": null
}
```

구성(config)에는 `id: 255 ignore`가 있어도 **export의 `classes.json`에는 포함하지 않습니다** (내보내기 마스크에 ignore 없음).

---

## 5. 타일·원본 식별 (tiles_manifest.json, sources_catalog.json)

### tiles_manifest.json (배열)

```json
[
  {
    "tile_id": "tile_000000_000896",
    "image_path": "images/tile_000000_000896.png",
    "mask_path": "masks/tile_000000_000896.png",
    "source_image_id": "source_0000",
    "source_image_name": "(B060)정사영상_2025_34602097.tif",
    "source_image_hash": "sha256:abcd...",
    "x": 0,
    "y": 896,
    "width": 1024,
    "height": 1024,
    "overlap": 128,
    "has_foreground": true,
    "foreground_ratio": 0.137,
    "measured_gsd_x_cm": 2.0,
    "measured_gsd_y_cm": 2.0,
    "gsd_source": "geotiff_transform"
  }
]
```

| 필드 | 설명 |
|------|------|
| `source_image_id` | 이 export 내에서 붙는 ID (`source_0000`). **동일 원본이라도 다른 export/build 순서에서 숫자가 달라질 수 있음** — 교차 실행 추적에는 **`source_image_hash` 또는 `sources_catalog.json`** 사용. |
| `source_image_hash` | `raw_geotiff/{파일명}` 내용 기준 SHA-256 (`sha256:` 접두사). 이름이 바뀌어도 내용이 같으면 같음. 원본 미존재 시 `null`. |
| `source_image_name` | 타일 메타의 원본 파일명 |

### sources_catalog.json (선택, 원본별 한 줄 요약)

`tiles_manifest.json`와 동일하게 **`source_image_hash`** 키를 사용합니다.

```json
{
  "source_0000": {
    "source_image_name": "(B060)정사영상_2025_34602097.tif",
    "source_image_hash": "sha256:..."
  }
}
```

---

## 6. 분할 (splits/)

### 각 split 파일 (예: train.json)

```json
{
  "split_strategy": "group_by_source_image",
  "items": ["tile_...", "tile_..."],
  "source_image_ids": ["source_0000", "source_0002"]
}
```

- `split_strategy`: 이 파일의 실제 적용 방식 (**`dataset_manifest.actual_split_strategy`와 일치**).
- **`source_image_ids`** — 해당 split에 할당된 `source_image_id` 목록 (파일명이 아님; 과거 `source_images` 키는 더 이상 쓰지 않음).

### source_groups.json (키는 `source_image_id`와 동일)

```json
{
  "source_0000": {
    "source_image_name": "(B060)정사영상_2025_34602097.tif",
    "tiles": ["tile_000000_005376", "..."]
  }
}
```

---

## 7. 데이터셋 메타데이터 (dataset_manifest.json)

분할 신뢰도:

| 필드 | 설명 |
|------|------|
| `requested_split_strategy` | 의도 (`group_by_source_image` 또는 `random`) |
| `actual_split_strategy` | 실제 적용 (**원본 종류 부족 시 `random`**) |
| `split_valid_group_leak_prevention` | `true`일 때만 래스터 단위 누수 방지 가능 |
| `split_warning` | fallback 이유 문자열 또는 `null` |
| `min_sources_required_for_group_split` | 기본 3 (group 전환 최소 **서로 다른** 원본 이름 수) |
| `distinct_source_images_count` | 메타에서 인식된 서로 다른 원본 파일명 수 |
| `same_source_may_span_train_val_test` | `random` 타일 분할 시 가능 |

전경 비율 (`pos_weight` 등에는 **train** 우선):

| 필드 | 설명 |
|------|------|
| `foreground_ratio_mean` | export 전체 타일 평균 |
| `train_foreground_ratio_mean` / `val_*` / `test_*` | split별 평균 |

예시 (원본 1종 → group 불가 시):

```json
{
  "requested_split_strategy": "group_by_source_image",
  "actual_split_strategy": "random",
  "split_valid_group_leak_prevention": false,
  "split_warning": "requested group_by_source_image but distinct source_image_name count (1) < 3: fallback to tile-level random split ...",
  "same_source_may_span_train_val_test": true,
  "min_sources_required_for_group_split": 3,
  "distinct_source_images_count": 1,
  "train_foreground_ratio_mean": 0.198,
  "val_foreground_ratio_mean": 0.231,
  "foreground_ratio_mean": 0.214
}
```

`split_strategy` 필드는 하위 호환용으로 **`actual_split_strategy`** 와 같은 값입니다.

---

## 8. validation_report.json

export 후 자동 생성. 예:

```json
{
  "image_count": 7,
  "pair_count": 7,
  "missing_masks": [],
  "missing_images": [],
  "invalid_mask_values": [],
  "invalid_image_modes": [],
  "invalid_mask_modes": [],
  "split_duplicates": [],
  "source_ids_spanned_across_splits": ["source_0000"],
  "split_leakage_by_source_detected": false,
  "same_source_may_span_train_val_test": true,
  "train_tile_count": 5,
  "train_foreground_ratio_mean": 0.198
}
```

- `split_leakage_by_source_detected`: **`actual_split_strategy == group_by_source_image`** 인데 같은 `source_image_id`(unknown 제외)가 여러 split에 걸치면 **`true`(비정상).**

---

## 9. U-Net 학습 코드 요약

### split 로드

```python
def load_split(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else raw["items"]
```

### BCEWithLogitsLoss — target **float**, **`logits`와 같은 채널 차원** `(N, 1, H, W)`

배치 차원만 맞추면 됩니다. **`unsqueeze(1)`은 마스크가 이미 `(B, 1, H, W)`일 때는 쓰면 안 됩니다.**

**패턴 A — Dataset에서 마스크를 `(1, H, W)`로 반환**

```python
# Dataset.__getitem__
mask_t = torch.from_numpy(np.array(mask, dtype=np.float32) / 255.0).unsqueeze(0)  # (1, H, W)

# DataLoader 이후
# logits:       (B, 1, H, W)
# batched_mask: (B, 1, H, W)
loss = loss_fn(logits, batched_mask)
```

**패턴 B — Dataset에서 마스크를 `(H, W)`로 반환**

```python
# Dataset.__getitem__
mask_t = torch.from_numpy(np.array(mask, dtype=np.float32) / 255.0)  # (H, W)

# 학습 루프에서 채널 추가
loss = loss_fn(logits, batched_mask.unsqueeze(1))  # (B, H, W) → (B, 1, H, W)
```

위 둘 중 하나로 통일합니다.

### CrossEntropyLoss — target **long**, **(N, H, W)**

```python
mask_t = torch.from_numpy(np.array(mask, dtype=np.int64) // 255)
loss_fn = nn.CrossEntropyLoss()
# logits (B, 2, H, W)
```

### `pos_weight` — **`train_foreground_ratio_mean`** + `eps`

```python
m = json.loads((export_dir / "dataset_manifest.json").read_text())
fg = m.get("train_foreground_ratio_mean")
if fg is None:
    fg = m.get("foreground_ratio_mean") or 0.5
eps = 1e-6
w = torch.tensor([(1 - fg) / max(float(fg), eps)])
loss_fn = nn.BCEWithLogitsLoss(pos_weight=w)
```

---

## 10. 운영 권장 사항

- 학습 시작 시 **`actual_split_strategy`**, **`split_warning`**, **`same_source_may_span_train_val_test`** 를 로그에 남긴다.
- 원본 종류가 1개뿐이면 타일 무작위 split은 정상적인 fallback이며, 검증 신뢰도는 한계가 있어 **외부 래스터**로 보조 검증하는 것을 권장한다.
