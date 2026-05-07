# 설정 변경 가이드 (config_guide)

[labeling-tool-plan-v3.md §2](../labeling-tool-plan-v3.md) 설정 계층을 운영 관점에서 요약한다.

---

## 1. 세 계층

| 계층 | 저장 위치 | 내용 예시 | 반영 시점 |
|------|-----------|-----------|-----------|
| 환경 의존 (비밀·절대경로) | `.env` (git 제외) | `DATABASE_URL`, `SAM_CHECKPOINT_PATH`, `LABELING_CONFIG_PATH`, `DEFAULT_TENANT_ID` | 프로세스 시작 시 |
| 운영 시드 (기본값) | `config/labeling.dev.yaml`, `config/labeling.prod.yaml` (git 포함) | 타일 크기, overlap, grid, GSD 기대값, SAM variant, 클래스 정의 | **첫 실행** 시 DB로 import; 이후에는 DB 우선 |
| 런타임 변경 | SQLite `active_config` (+ `config_change_snapshots`) | 동일 구조의 `LabelingConfig` JSON | `POST /api/config` 즉시 (Step 2 구현 후) |

`.env`의 `LABELING_CONFIG_PATH`로 **dev/prod 중 어떤 YAML을 시드로 쓸지** 고른다.

---

## 2. 기존 데이터셋 불변 원칙

- `active_config`를 바꿔도 **이미 생성된 데이터셋의 타일·라벨·export 의미는 바뀌지 않는다**.
- 데이터셋 생성 시점의 설정은 `dataset_config_snapshots` (및 `config_snapshot.yaml`)에 **고정**된다.
- `tile_size` 등을 바꿔 적용하려면 **새 데이터셋(또는 새 버전)** 을 만들어야 한다.

---

## 3. YAML 편집 시 주의

- 키 구조·타입은 `backend/app/core/config_schema.py` 의 `LabelingConfig` 와 일치해야 한다.
- `sam.model_variant` 허용값은 코드의 `Literal` 및 [api_spec.yaml](./api_spec.yaml) 의 `SamModelVariant` enum 과 동기화된다.
- `split_ratio` 는 `train + val + test = 1.0` (허용 오차 1e-6).

---

## 4. 관련 문서

- [dataset_spec.md](./dataset_spec.md) — 디렉터리·mask·메타데이터
- [api_spec.yaml](./api_spec.yaml) — 설정·데이터셋 API
- [README](../README.md) — SAM 체크포인트·모델 variant 추가 절차
