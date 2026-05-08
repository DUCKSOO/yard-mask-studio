# 라벨링 기준표 v0.2

**문서 상태**: 작업자 온보딩·체크리스트 반영. 정사영상 샘플 확보 후 시각 예시(20장 이상)를 `docs/assets/` 에 추가한다.

---

## 1. 목적

드론 정사영상 타일에서 **점유(occupied)** / **비점유(non_occupied)** 영역을 픽셀 단위로 구분하고, 학습에 방해되는 영역은 **ignore(255)** 로 표시한다. 본 문서는 클래스 정의와 경계 판정 원칙을 고정한다.

**본 저장소(yard-mask-studio)의 범위는 라벨링·export까지**이며, 모델 학습·배포는 별도 MLOps 프로젝트에서 수행한다.

---

## 2. 작업 환경 준비

1. **백엔드·프론트 기동** — 팀에서 안내한 URL로 프론트엔드(Vite)에 접속한다. API는 보통 동일 호스트의 프록시 또는 `VITE_API_BASE_URL` 로 연결된다.
2. **tenant / dataset** — 사이드바 상단에 서버에 등록된 `tenant_id`(예: `default`)와 작업 중인 `dataset_id`를 입력한다. 데이터셋이 없으면 관리자에게 데이터셋 생성·타일 생성을 요청한다.
3. **타일 목록 새로고침** — 네트워크·권한 오류가 없는지 확인한다. 진행률 바(전체 / labeled / approved)로 대략적인 진행 상황을 볼 수 있다.
4. **설정** — 타일 크기·클래스 정의는 데이터셋 생성 시점 스냅샷에 묶인다. 전역 설정 변경은 관리자와 합의 후 진행한다.

---

## 3. 작업 흐름 (단계별)

1. **타일 선택** — `TileNavigator`에서 상태 필터·그리드로 타일을 고른다.
2. **클래스 선택** — `ClassPanel`에서 occupied(1) 등 라벨할 클래스를 고른다.
3. **SAM (선택)** — 점(+)/점(−)/박스로 프롬프트를 찍고 **SAM 실행**으로 후보를 받는다. 후보가 없거나 부족하면 브러시로 직접 칠한다.
4. **브러시·지우개** — **브러시**로 클래스를 칠하고, **지우개**는 배경(0)으로 지운다. **반경** 슬라이더로 굵기를 조절한다.
5. **Undo / Redo** — 실수 시 되돌린다.
6. **저장** — **저장** 버튼으로 annotation을 서버에 보낸다. 저장 시 타일 상태가 `labeled`로 바뀌고 검수 큐에 `pending`으로 올라갈 수 있다.
7. **검수** — `ReviewPanel`에서 승인(approved) / 거부(rejected)를 처리한다. 거부 시 사유를 남기면 이후 수정에 도움이 된다.
8. **Export (관리자·마일스톤 시점)** — 라벨이 충분히 쌓이면 **U-Net Export**로 ZIP을 받는다. MLOps로 넘길 데이터는 이 산출물을 기준으로 한다.

---

## 4. 도구·단축키

| 동작 | 방법 |
|------|------|
| Undo | **Ctrl+Z** (macOS: **Cmd+Z**) |
| Redo | **Ctrl+Y** (macOS: **Cmd+Y**) |
| 저장 | **Ctrl+S** / **Cmd+S** |
| 브러시 도구 | **B** |
| 지우개 | **E** |
| 이동(팬) | **P** |
| 확대·축소 | 마우스 **휠** |
| 캔버스 이동 | **휠 버튼** 드래그 |

입력 필드(`INPUT`, `TEXTAREA`, `SELECT`)에 포커스가 있을 때는 위 단축키가 동작하지 않는다(폼 입력과 충돌 방지).

---

## 5. 100장 라벨링 체크리스트 (권장)

목표를 **100장(타일)** 단위로 쪼개 진행한다. 숫자는 팀과 조정 가능하다.

| 세션 | 목표 | 세션 후 확인 |
|------|------|----------------|
| 1 | 25장 저장 | 진행률 바 labeled 증가, 검수 큐에 항목 생성 여부 |
| 2 | 누적 50장 | reject 사유 패턴 정리(반복 시 가이드 보완) |
| 3 | 누적 75장 | 중간 **U-Net Export** 1회 — ZIP·manifest 열어 샘플 수·split 확인 |
| 4 | 누적 100장 | 검수 approved 비율·남은 pending 처리, 최종 export |

- 세션마다 **다시 불러오기**로 저장이 디스크에 반영됐는지 가끔 확인한다.
- 동일 타일을 여러 사람이 건드리지 않도록 데이터셋/타일 범위를 나눈다.

---

## 6. 품질 기준 (보강)

- **ignore 남용 금지** — 불확실할 때만 ignore(255)를 쓴다. “귀찮아서” 전부 ignore로 두지 않는다.
- **경계선** — §3·§5의 원칙에 맞춰 1~2픽셀 모호 구간은 ignore, 그 외는 명확한 쪽으로 occupied/non을 택한다.
- **세션당 자체 점검** — 저장 직전 한 번 줌아웃해 전체 마스크가 의도와 맞는지 본다.
- **클래스 혼동** — occupied와 non_occupied는 “블록 점유” 관점에서 통일한다(§3·§4).

---

## 7. MLOps 인계 절차

1. **Export** — GUI **U-Net Export** 또는 API `POST /api/tenants/{tenant_id}/datasets/{dataset_id}/export/unet` 로 export id를 받는다.
2. **ZIP** — `GET /api/tenants/{tenant_id}/exports/{export_id}/download` 로 아카이브를 내려받거나, 서버 디스크의 `export_path` 디렉터리를 복사한다.
3. **요약 확인(자동화용)** — `GET /api/tenants/{tenant_id}/exports/{export_id}/summary` 로 `sample_count`, train/val/test split 길이, `tile_size`, `mask_schema_version`, `created_at` 등을 JSON으로 확인할 수 있다.
4. **포함 파일** — 일반적으로 다음이 같이 있다: `images/`, `masks/`, `splits/*.json`, `dataset_manifest.json`, `config_snapshot.yaml`, `classes.json`. 상세는 [dataset_spec.md](./dataset_spec.md).
5. **config_snapshot.yaml** — 해당 export가 어떤 라벨링 설정(타일 크기·클래스 스키마 등)으로 만들어졌는지 재현·감사용으로 남긴다.

---

## 8. 클래스 정의

| ID | 이름 | 의미 |
|----|------|------|
| 0 | non_occupied | 야드 바닥·통로 등 **블록에 점유되지 않은** 픽셀 |
| 1 | occupied | 컨테이너·차량·장비·적재물 등으로 **블록이 점유된** 픽셀 |
| 255 | ignore | 라벨을 학습에 쓰지 않을 픽셀 (경계 불확실·가림·섀도우 등) |

색상(hex)은 UI 표시용이며, **저장 mask는 반드시 grayscale class index** 이다 ([dataset_spec.md](./dataset_spec.md)).

---

## 9. occupied 판정 (요지)

- **블록 경계 안**에서 물체·적재가 차지하는 영역은 occupied.
- 동일 블록 내 빈 공간(바닥 노출)은 non_occupied.
- 사람·소형 장비만 보이고 블록 점유 여부가 불명확하면 **보수적으로 ignore** 또는 팀 합의 규칙에 따름 (초기에는 ignore 권장).

---

## 10. non_occupied 판정 (요지)

- 통로, 빈 슬롯, 노출된 포장면 등 **블록이 비어 보이는** 영역.
- 초점은 “U-Net이 블록 점유를 학습할 수 있는가”에 맞춘다.

---

## 11. ignore 사용 기준

다음은 **ignore(255)** 로 두는 것을 권장한다.

- **경계 불확실**: occupied/non 경계가 1~2픽셀 수준으로만 모호한 경우(해상도·그림자).
- **가림**: 건물·크레인 그림자·반사로 블록 내부가 안 보이는 영역.
- **이미지 결함**: 압축 아티팩트, 구름, 렌즈 먼지 등으로 판단 불가.
- **도구 범위 밖**: 본 프로젝트 1차 범위에서 제외하기로 한 객체(예: 도로만 보이는 영역 등)는 팀 합의 후 ignore 또는 non_occupied 중 하나로 통일.

---

## 12. 시각 예시 (TODO)

정사영상 타일 예시를 확보한 뒤 아래에 삽입한다.

```markdown
<!-- 예: ![occupied 예시](./assets/labeling_01_occupied.png) -->
```

- 최소 권장: occupied-only, non-only, ignore-heavy, 경계 모호, 그림자, 소형 장비 각각 3장 이상.

---

## 13. 버전

- `classes.schema_version` (설정 YAML)과 본 문서의 기준 변경 시 버전을 맞춘다.
- 클래스 정의 변경 시 기존 라벨 **마이그레이션**이 필요하다 (설계서 §2.2).
