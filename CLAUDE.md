# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

중심지 폴리곤을 공간 분석을 통해 위계별로 분류하는 QGIS 플러그인이다. 두 격자 데이터셋과의 공간 교차 분석을 수행하여 중심지를 4단계 위계로 분류한다.

**위계 분류 (cascade 구조):**
- **광역중심지** — 최상위 (조건 1 + 조건 2 + 조건 3·4 AND 동시 충족)
- **지역중심지** — 중위 (조건 1 + 조건 2 충족)
- **생활중심지** — 기초 (조건 1만 충족)
- **이외** — 기준 미달

## 배포 (소스 → QGIS 플러그인 폴더 동기화)

QGIS는 자체 Python 인터프리터를 사용하므로 pip 설치나 별도 빌드 단계가 없다. 파일 수정 후 아래 명령으로 QGIS 플러그인 폴더에 복사하고 QGIS를 재시작하거나 플러그인 리로더로 재로드한다.

```bash
SRC="C:/Users/SEC/claude/cnt_classifier"
DEST="C:/Users/SEC/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/cnt_classifier"

# 개별 파일 복사 (수정된 파일만)
cp "$SRC/classifier.py"           "$DEST/classifier.py"
cp "$SRC/processor.py"            "$DEST/processor.py"
cp "$SRC/worker.py"               "$DEST/worker.py"
cp "$SRC/renderer.py"             "$DEST/renderer.py"
cp "$SRC/ui/tab_classify.py"      "$DEST/ui/tab_classify.py"
# 다른 파일도 동일 패턴으로 복사
```

테스트/린트 도구 없음 — QGIS Python 콘솔 또는 플러그인 재로드 후 직접 실행하여 검증한다.

## 아키텍처: 데이터 흐름

```
AnalysisConfig (shared mutable dataclass)
       │
       ├─ Tab1InputWidget      → 파일 경로 설정
       ├─ Tab2AnalysisWidget   → GeojeomConfig, InfraConfig, output_path 설정
       └─ Tab3ClassifyWidget   → ClassifyConfig, emd_layer_path 설정
```

`dialog.py`가 단일 `AnalysisConfig()` 인스턴스를 생성해 세 탭 모두에 레퍼런스로 전달한다. 한 탭의 변경이 즉시 다른 탭에 반영된다. Processing 알고리즘 경로(`alg_extract.py`, `alg_classify.py`)는 `AnalysisConfig`를 직접 생성해 `SpatialProcessor`에 전달한다.

### 탭 활성화 순서 (dialog.py)

1. Tab 2는 Tab 1에서 레이어 3개가 모두 선택되어야 활성화
2. Tab 3는 Tab 2 분석(`execute()`)이 완료되어야 활성화
3. Tab 2 설정 변경 시 `build_output_field_names(config)`를 호출해 Tab 3의 조건 필드 드롭다운을 즉시 갱신

### 출력 필드명 단일 소스

`utils.build_output_field_names(config)` 가 출력 GeoPackage 스키마와 Tab 3 드롭다운 양쪽의 단일 소스다. 새 통계 필드를 추가할 때는 이 함수, `processor.py`의 통계 계산, 그리고 `models.py`의 관련 StatType을 모두 함께 수정해야 한다.

## 핵심 파일 설명

### processor.py — `SpatialProcessor`

공간 분석의 핵심. `QgsSpatialIndex`로 격자 셀 내 폴리곤 교차 조회 후 통계 계산.

**공간 교차 방식**: `_get_intersecting()`은 격자 셀의 **중심점(centroid)이 중심지 폴리곤 내부에 포함**되는지 확인한다 (폴리곤 vs 폴리곤 교차가 아님). 격자 셀은 하나의 중심지에만 귀속된다.

**QGIS API 호환**: `_write_geopackage()`는 `QgsVectorFileWriter.create()`(3.20+)를 먼저 시도하고 실패하면 구버전 생성자로 폴백한다.

**레이어 로드**: `_load_layers()`는 `ogr` 프로바이더로 먼저 시도하고, 실패 시 현재 프로젝트에 로드된 레이어 중 `.source()`가 일치하는 것을 반환한다. Processing 알고리즘에서 임시(메모리) 레이어를 입력으로 사용할 때 이 폴백이 작동한다.

메서드 실행 순서:

- `execute()` — Phase 1: 레이어 로드 → 공간 인덱스 → 통계 계산 → GeoPackage 저장
- `execute_dedup()` — Phase 1.5: 읍면동별 중복 제거 (res_pop_sum 최대값만 보존)
- `execute_phase2()` — Phase 2: 기존 GeoPackage에 `분류` 필드 추가·업데이트
- `execute_delete_outside()` — `분류 == "이외"` 피처 삭제

### worker.py — 비동기 실행

`AnalysisWorker`: Phase 1(`execute()`)만 실행.  
`ClassifyWorker`: `execute_dedup()` → `execute_phase2()` → `execute_delete_outside()` 항상 순서대로 실행. **다이얼로그 경로에는 "이외" 삭제 여부를 선택하는 옵션이 없다** — 항상 삭제된다. (Processing 경로의 `alg_classify.py`에는 `DELETE_OUTSIDE` 불리언 파라미터가 있음.)

### classifier.py — `ConditionEvaluator`

설정된 임계값과 `Operator` 열거형으로 각 피처의 분류를 결정하는 순수 함수형 로직. 외부 QGIS 의존성 없음.

### models.py — 설정 dataclass

- `GeojeomConfig` — 국토공간거점지도 필드명 및 통계 종류
- `InfraConfig` — 생활인프라 컬럼 목록 및 집계 설정
- `ClassifyConfig` — 3단계 분류 조건 임계값
- `AnalysisConfig` — 마스터 컨테이너 (파일 경로 + 위 3개 config 포함)

### renderer.py

분류 완료 후 `분류` 필드 기준으로 4개 카테고리 심볼 적용 및 프로젝트에 레이어 추가. `add_emd_layer()`, `add_sgg_layer()`는 경계선만 표시하는 오버레이 레이어 추가.

### processing/ — Processing 알고리즘

Processing 알고리즘은 `processor.py`의 메서드를 직접 호출하는 래퍼다. 별도 로직을 구현하지 않는다. 도구 순서: 후보 추출 → 속성 추출 → 위계 설정.

- `alg_extract_candidates.py`: 국토공간거점지도 격자에서 중심지 후보 폴리곤 추출. 후보그룹1(중심지 유형 기반)·후보그룹2(거주인구밀도 기반) 두 그룹을 처리하며, 읍면동 이름 할당 시 끝글자(읍·면·동)를 제거하고 동일 읍면동 내 중복은 `_2`, `_3` 형식으로 suffix 추가.
- `alg_extract.py`: `SpatialProcessor.execute()` 호출. `postProcessAlgorithm()`에서 출력 GeoPackage의 `분류결과` 레이어를 지도 뷰에 자동 추가.
- `alg_classify.py`: 입력 레이어 source에서 `|layername=분류결과` 제거 후 `execute_dedup()` → `execute_phase2()` → `execute_delete_outside()` 호출.

## 입력/출력 데이터

| 데이터 | 주요 필드 |
| ------ | --------- |
| 중심지 후보(도형) | (사용자 정의) |
| 국토공간거점지도 | `pop_r`, `pop_w`, `pc_in`, `pc_out` |
| 생활인프라충족도 (500m) | `kg_ox`, `el_ox`, ... |

출력 GeoPackage 레이어명: `분류결과`  
주요 출력 필드: `res_pop_*`, `wor_pop_*`, `inflow_*`, `outflow_*`, `total_fac_*`, `vill_fac_*`, `base_fac_*`, `분류`

## 코드 작성 규칙

- UI 텍스트와 필드명은 **한국어** 사용
- 설정값은 `models.py`의 dataclass로 정의하고 UI → 로직으로 전달 (직접 하드코딩 금지)
- 무거운 처리는 반드시 `QgsTask` 워커로 비동기 실행 (다이얼로그 경로) 또는 `processAlgorithm()` 내 동기 실행 (Processing 경로)
- 공간 쿼리에는 `QgsSpatialIndex` 사용 (브루트포스 순회 금지)
- 좌표계가 다른 레이어 간에는 `QgsCoordinateTransform`으로 변환 처리
- Processing 알고리즘은 `processor.py`의 기존 메서드를 재사용하고 별도 로직을 중복 구현하지 않는다
